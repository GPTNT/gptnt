"""The `run.yaml` manifest schema and its loader.

This module is the single source of truth for the declarative run manifest. It is shared by `gptnt
doctor <run.yaml>` (which structurally validates + cross-checks the manifest) and the `gptnt run`
capstone (which executes it). It is deliberately framework-free: it does not import typer, so the
loader can be reused outside the CLI. The loader only validates *structure* — it does not check
whether referenced model/provider/anchor/experiment config names actually exist on disk (that
cross-check belongs to the doctor command).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from gptnt.experiments.ledger.base import Source
from gptnt.players.specification import PlayerSpec

if TYPE_CHECKING:
    from pathlib import Path

_SUPPORTED_SPEC_VERSION = 2


class Anchors(BaseModel):
    """The reference players a run compares against (resolved to player names later)."""

    model_config = ConfigDict(extra="forbid")

    best_expert: str | None = None
    """A model config name to use as the canonical expert."""

    best_defuser: str | None = None
    """A model config name to use as the canonical defuser."""


class RunManifest(BaseModel):
    """A complete, validated `run.yaml` manifest."""

    model_config = ConfigDict(extra="forbid")

    spec_version: int = 2
    suites: list[str] = Field(min_length=1)
    """One or more suite ids (`configs/suites/<id>.yaml`)."""

    rooms: int = Field(ge=1)
    displays: list[Annotated[int, Field(ge=0)]] | None = Field(default=None, min_length=1)
    """X display numbers to spread rooms across, round-robin.

    `None` inherits the ambient `$DISPLAY`.
    """

    players: list[PlayerSpec] = Field(min_length=1)
    anchors: Anchors = Field(default_factory=Anchors)

    source: Source = Source.local
    """Where the resume check reads completion from: `local` (on-disk outputs) or `wandb`."""

    observability: Literal["full", "limited", "off"] = "limited"

    @classmethod
    def from_path(cls, path: Path) -> RunManifest:
        """Read and validate a `run.yaml` manifest from disk."""
        return cls.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))

    @field_validator("spec_version")
    @classmethod
    def _check_spec_version(cls, version: int) -> int:
        """Reject any manifest written against an unsupported spec version."""
        if version != _SUPPORTED_SPEC_VERSION:
            raise ValueError(
                f"unsupported spec_version {version!r}; only {_SUPPORTED_SPEC_VERSION} is supported"
            )
        return version
