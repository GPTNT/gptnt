"""A scripted, in-process stand-in for the KTANE game binary.

Two seams replace the real game:

1. `GameProcessManager` is patched so `start()` returns a fixed port without spawning the
   binary, and the process is reported alive.
2. The `KtaneClient` HTTP endpoints are mocked with `respx` by a phase machine:

   `setup` --(/startMission)--> `lights_off` --(/settimescale value>0)--> `lights_on` --> `ended`

The game advances from `lights_on` to `ended` after `steps_until_end` steps. Sync play drives those
steps by explicit `/timestep` calls and pauses the game in between; async play leaves the game
unpaused and never calls `/timestep`, so an unpaused game advances on each defuser `/action`
instead, standing in for the wall clock the real game runs on. On `ended` the bomb reads solved,
detonated, or timed out per `outcome`. The real `GameStateMonitor`, heartbeats, `GameStateWatcher`,
and `ExperimentRunner` all run unmodified on top of this.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

import httpx
from PIL import Image

from gptnt.ktane import process_manager
from gptnt.ktane.state.game import GameState

if TYPE_CHECKING:
    import pytest
    import respx

_FAKE_GAME_PORT = 19999

# A minimal but valid BombState body (camelCase, as the game emits it) with a single unsolved
# module — an empty module list would vacuously mark the bomb solved.
_BASE_BOMB_STATE: dict[str, Any] = {  # noqa: WPS407
    "seed": 234,
    "maxStrikes": 3,
    "currentStrikes": 0,
    "strikes": [],
    "isDetonated": False,
    "isSolved": False,
    "isLightOn": False,
    "bombSide": "front",
    "timerModule": {"secondsRemaining": 300.0, "onFront": True, "index": 0, "name": "Timer"},
    "widgets": [{"serialNumber": "AB1CD2", "position": "right", "name": "SerialNumber"}],
    "modules": [
        {
            "wires": [{"position": 0, "isCut": False, "color": "red"}],
            "isSolved": False,
            "inFocus": False,
            "onFront": True,
            "index": 1,
            "name": "Wires",
        }
    ],
}


def _blank_frame_buffer(width: int = 64, height: int = 64) -> bytes:
    """Pack a single blank RGB frame the way `FrameBuffer` expects (header + pixels)."""
    image = Image.new("RGB", (width, height), color=(20, 20, 20))
    pixels = image.transpose(Image.Transpose.FLIP_TOP_BOTTOM).tobytes()
    header = struct.pack("<Biii", 0, 1, height, width)  # has_segmentation=0, frame_count=1
    return header + pixels


@dataclass
class FakeKtaneGame:
    """Scripted KTANE game: a phase machine exposed over the mocked HTTP endpoints."""

    port: int = _FAKE_GAME_PORT
    steps_until_end: int = 2
    outcome: Literal["solved", "detonated", "timed_out"] = "solved"
    num_modules: int = 1
    modules_solved_at_end: int = 0
    """How many modules read as solved on a losing end, for a partial-solve bomb."""

    phase: Literal["setup", "lights_off", "lights_on", "ended"] = field(
        default="setup", init=False
    )
    unpaused: bool = field(default=False, init=False)
    timesteps: int = field(default=0, init=False)
    actions_sent: int = field(default=0, init=False)
    hits: dict[str, int] = field(default_factory=dict, init=False)
    _frame_bytes: bytes = field(default_factory=_blank_frame_buffer, init=False, repr=False)

    @property
    def base_url(self) -> str:
        """Base URL the patched game process reports."""
        return f"http://localhost:{self.port}"

    def install(self, respx_mock: respx.MockRouter, monkeypatch: pytest.MonkeyPatch) -> None:
        """Patch the process manager and register the HTTP routes against `respx_mock`."""

        async def _fake_start(_self: object) -> int:  # noqa: WPS430
            return self.port

        async def _fake_terminate(_self: object, **_kwargs: object) -> None:  # noqa: WPS430
            """No-op: the fake game has no OS process to terminate."""

        monkeypatch.setattr(process_manager.GameProcessManager, "start", _fake_start)
        monkeypatch.setattr(process_manager.GameProcessManager, "terminate", _fake_terminate)
        monkeypatch.setattr(
            process_manager.GameProcessManager, "is_alive", property(lambda _self: True)
        )

        routes = {
            "/health": self._on_health,
            "/startMission": self._on_start_mission,
            "/settimescale": self._on_set_timescale,
            "/timestep": self._on_timestep,
            "/action": self._on_action,
            "/state": self._on_state,
            "/buffer": self._on_buffer,
            "/detonate": self._on_detonate,
            "/solve": self._on_solve,
            "/reset": self._on_reset,
        }
        for path, handler in routes.items():

            def _record(  # noqa: WPS430
                request: httpx.Request, *, _handler: Any = handler, _path: str = path
            ) -> httpx.Response:
                self.hits[_path] = self.hits.get(_path, 0) + 1
                return _handler(request)

            _ = respx_mock.get(f"{self.base_url}{path}").mock(side_effect=_record)

    def _game_state(self) -> str:
        return {
            "setup": GameState.main_menu,
            "lights_off": GameState.lights_off,
            "lights_on": GameState.lights_on,
            "ended": GameState.game_ended,
        }[self.phase].value

    def _bomb_state(self) -> dict[str, Any]:
        state = {**_BASE_BOMB_STATE}
        state["isLightOn"] = self.phase in {"lights_on", "ended"}
        state["modules"] = self._modules()
        if self.phase == "ended":
            self._apply_terminal_state(state)
        return state

    def _modules(self) -> list[dict[str, Any]]:
        """Build `num_modules` module states, marking the ones solved at the current phase."""
        template = _BASE_BOMB_STATE["modules"][0]
        solved = self._modules_solved()
        return [
            {**template, "index": index + 1, "isSolved": index < solved}
            for index in range(self.num_modules)
        ]

    def _modules_solved(self) -> int:
        """How many modules read as solved: all on a win, `modules_solved_at_end` on a loss."""
        if self.phase != "ended":
            return 0
        return self.num_modules if self.outcome == "solved" else self.modules_solved_at_end

    def _apply_terminal_state(self, state: dict[str, Any]) -> None:
        """Set the losing-end flags; the modules already carry the solved count from `_modules`.

        `is_timed_out` and `is_strike_out` both require `is_detonated`, so a detonation is the base
        of every losing end and the timer or strike count is what distinguishes them.
        """
        if self.outcome == "solved":
            state["isSolved"] = True
            return
        state["isDetonated"] = True
        if self.outcome == "timed_out":
            state["timerModule"] = {**state["timerModule"], "secondsRemaining": 0}

    # --- HTTP handlers -----------------------------------------------------------------------
    def _on_health(self, _request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=self._game_state())

    def _on_start_mission(self, _request: httpx.Request) -> httpx.Response:
        assert self.phase == "setup", (
            f"startMission called in phase {self.phase!r} — expected 'setup'. "
            "ExperimentRunner call order has changed."
        )
        self.phase = "lights_off"
        return httpx.Response(200, text="true")

    def _on_set_timescale(self, request: httpx.Request) -> httpx.Response:
        # value>0 unpauses the game (and turns the lights on); value==0 pauses it. Sync mode pauses
        # between steps and advances time by explicit `/timestep`; async mode leaves the game
        # unpaused and never steps it, so an unpaused game advances on each defuser `/action`.
        value = float(request.url.params.get("value", "0"))
        self.unpaused = value > 0
        if self.unpaused and self.phase == "lights_off":
            self.phase = "lights_on"
        return httpx.Response(200, text="true")

    def _on_timestep(self, _request: httpx.Request) -> httpx.Response:
        assert self.phase in {"lights_on", "ended"}, (
            f"timestep called in phase {self.phase!r} — expected 'lights_on'. "
            "ExperimentRunner call order has changed."
        )
        if self.phase == "lights_on":
            self._advance()
        return httpx.Response(200, text="true")

    def _advance(self) -> None:
        """Advance one step towards the end; the bomb resolves per `outcome` once time runs out."""
        self.timesteps += 1
        if self.timesteps >= self.steps_until_end:
            self.phase = "ended"

    def _on_action(self, _request: httpx.Request) -> httpx.Response:
        self.actions_sent += 1
        # Async play never calls `/timestep`, so the defuser's own actions drive time forward while
        # the game is unpaused. Sync play stays paused here and advances by `/timestep` instead.
        if self.unpaused and self.phase == "lights_on":
            self._advance()
        return httpx.Response(200, text="true")

    def _on_state(self, _request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=self._bomb_state())

    def _on_buffer(self, _request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=self._frame_bytes)

    def _on_detonate(self, _request: httpx.Request) -> httpx.Response:
        self.phase = "ended"
        self.outcome = "detonated"
        return httpx.Response(200, text="true")

    def _on_solve(self, _request: httpx.Request) -> httpx.Response:
        self.phase = "ended"
        self.outcome = "solved"
        return httpx.Response(200, text="true")

    def _on_reset(self, _request: httpx.Request) -> httpx.Response:
        self.phase = "setup"
        self.timesteps = 0
        return httpx.Response(200, text="true")
