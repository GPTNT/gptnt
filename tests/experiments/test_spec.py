from gptnt.experiments.spec import ExperimentSpec

from tests._factories.experiments import (
    make_experiment_instance,
    make_experiment_spec,
    make_manual_profile,
)


def test_fingerprint_ignores_attempt_and_player_names() -> None:
    """Specs that differ only in attempt or player identity fingerprint the same experiment."""
    spec = make_experiment_spec()
    same_experiment = spec.model_copy(
        update={"attempt": spec.attempt + 1, "defuser_name": "other"}
    )
    assert spec.fingerprint == same_experiment.fingerprint


def test_fingerprint_includes_manual_profile_but_not_player_image_dimensions() -> None:
    """The profile is spec identity.

    Image dimensions are resolved runtime state.
    """
    instance = make_experiment_instance()
    different_manual = instance.model_copy(
        update={"manual_profile": make_manual_profile(document_id="BigButton")}
    )
    different_image_dimensions = instance.model_copy(
        update={
            "defuser_capabilities": instance.defuser_capabilities.model_copy(
                update={"image_dimensions": (640, 480)}
            )
        }
    )

    assert instance.fingerprint != different_manual.fingerprint
    assert instance.fingerprint == different_image_dimensions.fingerprint


def test_rule_seed_changes_mission_and_experiment_identity() -> None:
    """Generated rules distinguish mission keys, fingerprints, and spec output paths."""
    spec = make_experiment_spec()
    different_rules = spec.model_copy(
        update={
            "mission_spec": spec.mission_spec.model_copy(
                update={"rule_seed": spec.mission_spec.rule_seed + 1}
            )
        }
    )

    assert spec.mission_spec.mission_key != different_rules.mission_spec.mission_key
    assert spec.fingerprint != different_rules.fingerprint
    assert spec.attempt_name != different_rules.attempt_name


def test_fingerprint_is_stable_across_a_serialisation_round_trip() -> None:
    """Serialising the spec computes the fingerprint without recursing, and it survives reload."""
    spec = make_experiment_spec()
    reloaded = ExperimentSpec.model_validate_json(spec.model_dump_json())
    assert reloaded.fingerprint == spec.fingerprint
