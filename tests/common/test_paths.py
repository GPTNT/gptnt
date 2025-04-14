from pathlib import Path

import pytest

from gptnt.common.paths import Paths


def test_paths_work_as_expected_with_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    before = Paths()
    monkeypatch.setenv("CONFIGS", "new_config")
    after = Paths()
    assert before != after
    assert after.configs == Path("new_config")
