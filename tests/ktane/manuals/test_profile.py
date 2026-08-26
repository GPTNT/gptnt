"""Manual profile configuration validation."""

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from gptnt.common.paths import Paths
from gptnt.ktane.manuals.profile import LocalDocument, ManualProfile

# Profile parsing


def test_every_shipped_config_parses() -> None:
    """Load every concrete profile through the model used by configuration composition."""
    for config in Paths().manual_profiles.glob("*.yaml"):
        if config.name.startswith("_"):
            continue
        _ = ManualProfile.model_validate(yaml.safe_load(config.read_text()))


def test_local_document_rejects_a_non_html_path() -> None:
    """Restrict local manual inputs to HTML documents that dependency discovery can inspect."""
    with pytest.raises(ValidationError, match=r"must be an \.html file"):
        _ = LocalDocument(source="local", path=Path("my/notes/Wires.pdf"), language="en")
