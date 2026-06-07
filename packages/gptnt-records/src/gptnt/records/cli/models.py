from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass
class ExperimentsSource:
    """A single CLI token parsed into either a directory path or an experiment name."""

    kind: Literal["dir", "name"]
    raw: str

    @classmethod
    def from_cli_string(cls, raw: str) -> ExperimentsSource:
        """Parse a CLI token as either an existing directory or an experiment name stem."""
        path = Path(raw)
        if path.exists() and path.is_dir():
            return cls(kind="dir", raw=raw)
        return cls(kind="name", raw=raw)
