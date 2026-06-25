"""Factories for experiment-shaped test objects (descriptors, specs)."""

from __future__ import annotations

from uuid import uuid4

from whenever import Instant

from gptnt.experiments.descriptor import ExperimentDescriptor
from gptnt.experiments.spec import ExperimentSpec
from gptnt.ktane.mission_spec import KtaneMissionSpec
from gptnt.specification import PlayerCapabilities, PlayerProtocol


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
        condition="single_module",
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
