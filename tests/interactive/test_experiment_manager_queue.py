"""The Experiment Manager queue's attempt-name deduplication."""

import pytest
from fastapi import HTTPException
from pytest_mock import MockerFixture

from gptnt.interactive.services.experiment_manager.api import Specs, add_experiment_specs
from gptnt.interactive.services.experiment_manager.experiment_manager import ExperimentManager

from tests._factories.experiments import make_experiment_spec


def _manager(mocker: MockerFixture) -> ExperimentManager:
    return ExperimentManager(redis=mocker.MagicMock(), redis_broker=mocker.MagicMock())


@pytest.mark.anyio
async def test_repeated_spec_is_idempotent(mocker: MockerFixture) -> None:
    manager = _manager(mocker)
    spec = make_experiment_spec()

    await add_experiment_specs(Specs(specs=[spec, spec]), manager)
    await add_experiment_specs(Specs(specs=[spec]), manager)

    assert manager.specs == [spec]


@pytest.mark.anyio
async def test_conflicting_spec_for_attempt_is_rejected(mocker: MockerFixture) -> None:
    manager = _manager(mocker)
    spec = make_experiment_spec()
    conflicting = spec.model_copy(
        update={
            "defuser_protocol": spec.defuser_protocol.model_copy(
                update={"receive_feedback_after_action": True}
            )
        }
    )

    with pytest.raises(HTTPException) as error:
        await add_experiment_specs(Specs(specs=[spec, conflicting]), manager)

    assert error.value.status_code == 409
    assert spec.attempt_name in str(error.value.detail)
    assert manager.specs == []
