"""The `ExperimentSpec.fingerprint` property that identifies what an experiment measures."""

from gptnt.experiments.spec import ExperimentSpec

from tests._factories.experiments import make_experiment_spec


def test_fingerprint_ignores_attempt_and_player_names() -> None:
    """Two specs that differ only in attempt or player identity fingerprint the same experiment."""
    spec = make_experiment_spec()
    same_experiment = spec.model_copy(
        update={"attempt": spec.attempt + 1, "defuser_name": "other"}
    )
    assert spec.fingerprint == same_experiment.fingerprint


def test_fingerprint_changes_when_the_experiment_changes() -> None:
    """A different mission is a different experiment, so its fingerprint must shift."""
    spec = make_experiment_spec(seed=1)
    different_mission = make_experiment_spec(seed=2)
    assert spec.fingerprint != different_mission.fingerprint


def test_fingerprint_is_stable_across_a_serialisation_round_trip() -> None:
    """Serialising the spec computes the fingerprint without recursing, and it survives reload."""
    spec = make_experiment_spec()
    reloaded = ExperimentSpec.model_validate_json(spec.model_dump_json())
    assert reloaded.fingerprint == spec.fingerprint
