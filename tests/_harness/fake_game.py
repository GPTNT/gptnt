"""A scripted, in-process stand-in for the KTANE game binary.

Two seams replace the real game (see plan Stage C):

1. `GameProcessManager` is patched so `start()` returns a fixed port without spawning the
   binary, and the process is reported alive.
2. The `KtaneClient` HTTP endpoints are mocked with `respx` by a tiny state machine that
   advances exactly on the calls the real runner makes:

   `Setup` --(/startMission)--> `LightsOff` --(/settimescale value>0)--> `LightsOn`
   --(N x /timestep)--> `PostGame`

The *real* `GameStateMonitor`, heartbeats, `GameStateWatcher` and `ExperimentRunner` all run
unmodified on top of this, so a full Defuser+Expert experiment runs to completion with no binary.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

import httpx
from PIL import Image

from gptnt.core.ktane import process_manager
from gptnt.core.ktane.state.game import GameState

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
    outcome: Literal["solved", "detonated"] = "solved"

    phase: Literal["setup", "lights_off", "lights_on", "ended"] = field(
        default="setup", init=False
    )
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
        if self.phase == "ended" and self.outcome == "solved":
            state["isSolved"] = True
            state["modules"] = [{**module, "isSolved": True} for module in state["modules"]]
        if self.phase == "ended" and self.outcome == "detonated":
            state["isDetonated"] = True
            state["currentStrikes"] = 3
        return state

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
        value = float(request.url.params.get("value", "0"))
        if value > 0:
            assert self.phase == "lights_off", (
                f"settimescale value>0 called in phase {self.phase!r} — expected 'lights_off'. "
                "ExperimentRunner call order has changed."
            )
            self.phase = "lights_on"
        return httpx.Response(200, text="true")

    def _on_timestep(self, _request: httpx.Request) -> httpx.Response:
        assert self.phase in {"lights_on", "ended"}, (
            f"timestep called in phase {self.phase!r} — expected 'lights_on'. "
            "ExperimentRunner call order has changed."
        )
        if self.phase == "lights_on":
            self.timesteps += 1
            if self.timesteps >= self.steps_until_end:
                self.phase = "ended"
        return httpx.Response(200, text="true")

    def _on_action(self, _request: httpx.Request) -> httpx.Response:
        self.actions_sent += 1
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
