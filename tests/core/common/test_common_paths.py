from pathlib import Path

import pytest

from gptnt.common.paths import Paths


def test_paths_work_as_expected_with_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    before = Paths()
    monkeypatch.setenv("CONFIGS", "new_config")
    after = Paths()
    assert before != after
    assert after.configs == Path("new_config")


def test_configs_prefers_local_checkout_dir(tmp_path: Path) -> None:
    (tmp_path / "configs").mkdir()
    assert Paths(root=tmp_path).configs == tmp_path / "configs"


def test_configs_falls_back_to_packaged_copy(tmp_path: Path) -> None:
    # No `root/configs` here, so `configs` resolves to the packaged `gptnt/_configs`. A source
    # checkout has no `_configs` on disk, so the fallback's end-to-end presence is verified by the
    # wheel build (integration); here we only check the fallback location is chosen.
    resolved = Paths(root=tmp_path).configs
    assert resolved.name == "_configs"
    assert tmp_path not in resolved.parents


def test_experiment_recorder_outputs_uses_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    paths = Paths()
    assert paths.experiment_outputs != Path("custom_outputs")
    monkeypatch.setenv("EXPERIMENT_RECORDER_OUTPUTS", "custom_outputs")
    paths_with_env = Paths()
    assert paths_with_env.experiment_outputs == Path("custom_outputs")
