"""The Experiment Manager queue's attempt-name deduplication."""

import pytest
from pytest_mock import MockerFixture

from gptnt.interactive.services.experiment_manager.api import Specs, add_experiment_specs
from gptnt.interactive.services.experiment_manager.experiment_manager import ExperimentManager

from tests._factories.experiments import make_experiment_spec


def _manager(mocker: MockerFixture) -> ExperimentManager:
    return ExperimentManager(redis=mocker.MagicMock(), redis_broker=mocker.MagicMock())


@pytest.mark.anyio
async def test_repeated_attempt_names_are_ignored(mocker: MockerFixture) -> None:
    """The first submitted spec wins when a request repeats its attempt name."""
    manager = _manager(mocker)
    spec = make_experiment_spec()
    conflicting = spec.model_copy(
        update={
            "defuser_protocol": spec.defuser_protocol.model_copy(
                update={"receive_feedback_after_action": True}
            )
        }
    )

    await add_experiment_specs(Specs(specs=[spec, conflicting]), manager)

    assert manager.specs == [spec]
