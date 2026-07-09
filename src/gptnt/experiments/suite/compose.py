from __future__ import annotations

from typing import TYPE_CHECKING

import hydra

from gptnt.common.hydra import load_config

if TYPE_CHECKING:
    from gptnt.experiments.suite.core import Suite

CONFIG_NAME = "suite_generator"


def compose_suite(suite_name: str) -> Suite:
    """Compose and instantiate one suite by name from its live config (the authoring path).

    Used by `gptnt suite freeze` to snapshot the live `configs/suites/` folder. Generation reads
    from the lock instead (`SuiteLock.load_suite`).
    """
    return hydra.utils.instantiate(
        load_config(config_name=CONFIG_NAME, overrides=[f"suites={suite_name}"]).suite
    )
