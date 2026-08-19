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


def test_fingerprint_tracks_manual_profile_not_player_dimensions() -> None:
    """The frozen manual changes the experiment; runtime image dimensions do not."""
    spec = make_experiment_spec()
    different_manual = spec.model_copy(
        update={"manual_profile": make_manual_profile(document_id="BigButton")}
    )
    instance = make_experiment_instance(spec)
    resized_instance = instance.model_copy(
        update={
            "defuser_capabilities": instance.defuser_capabilities.model_copy(
                update={"image_dimensions": (640, 480)}
            )
        }
    )

    assert spec.fingerprint != different_manual.fingerprint
    assert spec.fingerprint == instance.fingerprint == resized_instance.fingerprint


def test_fingerprint_is_stable_across_a_serialisation_round_trip() -> None:
    """Serialising the spec computes the fingerprint without recursing, and it survives reload."""
    spec = make_experiment_spec()
    reloaded = ExperimentSpec.model_validate_json(spec.model_dump_json())
    assert reloaded.fingerprint == spec.fingerprint
