"""Factories for experiment-shaped test objects (descriptors, specs, summaries)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

from whenever import Instant

from gptnt.experiments.descriptor import ExperimentDescriptor
from gptnt.experiments.models import ExperimentSummary
from gptnt.experiments.spec import ExperimentSpec
from gptnt.ktane.mission_spec import KtaneMissionSpec
from gptnt.ktane.state.bomb import BombState
from gptnt.players.specification import PlayerCapabilities, PlayerProtocol

if TYPE_CHECKING:
    from collections.abc import Sequence

    from gptnt.players.specification import CommunicationStyle


def make_solved_bomb() -> BombState:
    """A solved bomb (empty modules; the is-solved validator marks an empty bomb solved)."""
    return BombState.model_validate(
        {
            "seed": 1,
            "maxStrikes": 3,
            "strikes": None,
            "isDetonated": False,
            "isSolved": True,
            "isLightOn": True,
            "bombSide": "front",
            "timerModule": {
                "name": "Timer",
                "onFront": True,
                "index": 0,
                "secondsRemaining": 100.0,
            },
            "widgets": [],
            "modules": [],
        }
    )


def make_experiment_spec(seed: int = 12345) -> ExperimentSpec:
    """A real single-player ExperimentSpec; the seed makes each attempt_name distinct."""
    return ExperimentSpec(
        mission_spec=KtaneMissionSpec(
            seed=seed,
            time_limit=300,
            num_strikes_allowed=3,
            components=["Wires"],
            optional_widgets=1,
            needy_time=60,
        ),
        mission_set="single_module",
        suite_name="single-parametric-sync",
        suite_revision=1,
        defuser_protocol=PlayerProtocol(
            role="defuser",
            communication_style="sync",
            is_playing_alone=True,
            include_manual=False,
            receive_feedback_after_action=False,
            allow_magic_actions=False,
        ),
        defuser_name="test-defuser",
        expert_protocol=None,
        expert_name=None,
    )


def make_experiment_descriptor(spec: ExperimentSpec | None = None) -> ExperimentDescriptor:
    """A real single-player ExperimentDescriptor (no expert)."""
    return ExperimentDescriptor(
        experiment_spec=spec or make_experiment_spec(),
        session_id=uuid4(),
        defuser_uuid=uuid4(),
        expert_uuid=None,
        game_uuid=uuid4(),
        start_time=Instant.now(),
        defuser_capabilities=PlayerCapabilities(player_name="test-defuser", player_type="ai"),
        expert_capabilities=None,
    )


def make_experiment_summary(
    *,
    defuser_name: str = "test-defuser",
    expert_name: str | None = None,
    modules: Sequence[str] = ("Wires", "Keypad"),
    num_modules_solved: int = 2,
    is_solved: bool = True,
    is_timed_out: bool = False,
    is_strike_out: bool = False,
    is_hard_crash: bool = False,
    strike_count: int = 0,
    seconds_remaining: float = 60.0,
    communication_style: CommunicationStyle = "sync",
    mission_set: str = "multiple_modules_2",
    seed: int = 12345,
) -> ExperimentSummary:
    """A real ExperimentSummary; defaults to a valid, fully-solved multi-module mission."""
    descriptor = make_experiment_descriptor()
    return ExperimentSummary(
        attempt_name=f"{mission_set}_{defuser_name}_{seed}",
        session_id=descriptor.session_id,
        mission_set=mission_set,
        seed=seed,
        pairing=f"(defuser={defuser_name})",
        defuser_name=defuser_name,
        expert_name=expert_name,
        communication_style=communication_style,
        attempt=1,
        modules=list(modules),
        is_solved=is_solved,
        is_detonated=not is_solved,
        is_timed_out=is_timed_out,
        is_strike_out=is_strike_out,
        seconds_remaining=seconds_remaining,
        strike_count=strike_count,
        num_modules_solved=num_modules_solved,
        is_hard_crash=is_hard_crash,
        experiment_descriptor=descriptor,
        defuser_capabilities=descriptor.defuser_capabilities,
        expert_capabilities=None,
        gptnt_version="1.0.0",
        git_sha=None,
    )
