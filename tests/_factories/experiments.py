"""Factories for experiment specs, instances, and summaries."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

from whenever import Instant

from gptnt.experiments.instance import ExperimentInstance
from gptnt.experiments.models import ExperimentSummary
from gptnt.experiments.spec import ExperimentSpec
from gptnt.ktane.manuals.definition import MANUAL_COMPILER_SCHEMA, ManualBuildDefinition
from gptnt.ktane.manuals.profile import KtaneContentDocument, ManualProfile
from gptnt.ktane.manuals.sources import (
    KtaneContentCatalogSource,
    KtaneContentSource,
    ManualSources,
)
from gptnt.ktane.mission_spec import KtaneMissionSpec
from gptnt.ktane.state.bomb import BombOutcome, BombState
from gptnt.players.specification import PlayerCapabilities, PlayerProtocol

if TYPE_CHECKING:
    from collections.abc import Sequence

    from gptnt.players.specification import CommunicationStyle


def make_manual_build_definition() -> ManualBuildDefinition:
    """A small English manual build definition for experiment-model tests."""
    return ManualBuildDefinition(
        profile=ManualProfile(
            include_frontmatter=False,
            documents=(KtaneContentDocument(source="ktanecontent", id="Wires", language="en"),),
        ),
        sources=ManualSources(
            ktane_content=KtaneContentSource(
                repository="https://manual.test/content.git",
                commit="0" * 40,
                catalog=KtaneContentCatalogSource(url="https://manual.test/catalog.json"),
            ),
            official_manual={},
        ),
        language="en",
        rule_seed=1,
        compiler_schema=MANUAL_COMPILER_SCHEMA,
    )


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
        suite_revision=2,
        suite_digest="0" * 32,
        manual_build=make_manual_build_definition(),
        defuser_protocol=PlayerProtocol(
            role="defuser", communication_style="sync", is_playing_alone=True, include_manual=False
        ),
        defuser_name="test-defuser",
        expert_protocol=None,
        expert_name=None,
    )


def make_experiment_instance(spec: ExperimentSpec | None = None) -> ExperimentInstance:
    """A single-player experiment instance."""
    experiment_spec = spec or make_experiment_spec()
    expert_uuid = None
    expert_capabilities = None
    if experiment_spec.expert_name is not None:
        expert_uuid = uuid4()
        expert_capabilities = PlayerCapabilities(
            player_name=experiment_spec.expert_name, player_type="ai"
        )

    return ExperimentInstance.model_validate(
        experiment_spec.model_dump()
        | {
            "session_id": uuid4(),
            "defuser_uuid": uuid4(),
            "expert_uuid": expert_uuid,
            "game_uuid": uuid4(),
            "start_time": Instant.now(),
            "defuser_capabilities": PlayerCapabilities(
                player_name=experiment_spec.defuser_name, player_type="ai"
            ),
            "expert_capabilities": expert_capabilities,
        }
    )


def make_experiment_summary(
    *,
    defuser_name: str = "test-defuser",
    expert_name: str | None = None,
    modules: Sequence[str] = ("Wires", "Keypad"),
    num_modules_solved: int = 2,
    outcome: BombOutcome = BombOutcome.solved,
    is_hard_crash: bool = False,
    strike_count: int = 0,
    seconds_remaining: float = 60.0,
    communication_style: CommunicationStyle = "sync",
    mission_set: str = "multiple_modules_2",
    seed: int = 12345,
) -> ExperimentSummary:
    """An ExperimentSummary defaulting to a valid, fully-solved multi-module mission."""
    is_single_player = expert_name is None
    defuser_protocol = PlayerProtocol(
        role="defuser",
        communication_style=communication_style,
        is_playing_alone=is_single_player,
        include_manual=False,
    )
    expert_protocol = (
        None
        if expert_name is None
        else PlayerProtocol(
            role="expert",
            communication_style=communication_style,
            is_playing_alone=False,
            include_manual=True,
        )
    )
    spec = ExperimentSpec(
        mission_spec=KtaneMissionSpec(
            seed=seed,
            time_limit=300,
            num_strikes_allowed=3,
            components=list(modules),
            optional_widgets=1,
        ),
        mission_set=mission_set,
        suite_name="single-parametric-sync",
        suite_revision=2,
        suite_digest="0" * 32,
        manual_build=make_manual_build_definition(),
        defuser_protocol=defuser_protocol,
        defuser_name=defuser_name,
        expert_protocol=expert_protocol,
        expert_name=expert_name,
    )
    expert_uuid = None
    expert_capabilities = None
    if expert_name is not None:
        expert_uuid = uuid4()
        expert_capabilities = PlayerCapabilities(player_name=expert_name, player_type="ai")

    instance = ExperimentInstance.model_validate(
        spec.model_dump()
        | {
            "session_id": uuid4(),
            "defuser_uuid": uuid4(),
            "expert_uuid": expert_uuid,
            "game_uuid": uuid4(),
            "start_time": Instant.now(),
            "defuser_capabilities": PlayerCapabilities(player_name=defuser_name, player_type="ai"),
            "expert_capabilities": expert_capabilities,
        }
    )
    return ExperimentSummary.model_validate(
        instance.model_dump(exclude_computed_fields=True)
        | {
            "outcome": outcome,
            "seconds_remaining": seconds_remaining,
            "strike_count": strike_count,
            "num_modules_solved": num_modules_solved,
            "is_hard_crash": is_hard_crash,
            "gptnt_version": "0.1.0",
            "git_sha": None,
        }
    )
