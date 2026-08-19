from gptnt.experiments.spec import ExperimentSpec

from tests._factories.experiments import (
    make_experiment_instance,
    make_experiment_spec,
    make_manual_profile,
)


def test_fingerprint_ignores_attempt_and_player_names() -> None:
    """Two specs that differ only in attempt or player identity fingerprint the same experiment."""
    spec = make_experiment_spec()
    same_experiment = spec.model_copy(
        update={"attempt": spec.attempt + 1, "defuser_name": "other"}
    )
    assert spec.fingerprint == same_experiment.fingerprint


def test_fingerprint_includes_manual_profile_but_not_player_image_dimensions() -> None:
    """The profile is spec identity; image dimensions are resolved runtime state."""
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


def test_fingerprint_is_stable_across_a_serialisation_round_trip() -> None:
    """Serialising the spec computes the fingerprint without recursing, and it survives reload."""
    spec = make_experiment_spec()
    reloaded = ExperimentSpec.model_validate_json(spec.model_dump_json())
    assert reloaded.fingerprint == spec.fingerprint
