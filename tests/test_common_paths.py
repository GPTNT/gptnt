from pathlib import Path

import pytest

from gptnt.common.paths import Paths


def test_paths_work_as_expected_with_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    before = Paths()
    monkeypatch.setenv("CONFIGS", "new_config")
    after = Paths()
    assert before != after
    assert after.configs == Path("new_config")


def test_experiment_recorder_outputs_uses_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    paths = Paths()
    assert paths.experiment_outputs != Path("custom_outputs")
    monkeypatch.setenv("EXPERIMENT_RECORDER_OUTPUTS", "custom_outputs")
    paths_with_env = Paths()
    assert paths_with_env.experiment_outputs == Path("custom_outputs")
