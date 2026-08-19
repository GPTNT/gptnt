"""Frozen inputs that identify one compiled manual."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from gptnt.common.hashing import stable_digest
from gptnt.common.paths import Paths
from gptnt.ktane.manuals.profile import ManualProfile, OfficialDocument
from gptnt.ktane.manuals.sources import ManualSources

MANUAL_COMPILER_SCHEMA = "gptnt.manual.v1"


class ManualBuildDefinition(BaseModel):
    """The manual inputs stored when a suite revision is frozen.

    The profile order and selected source pins determine which source files the compiler must use.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    profile: ManualProfile
    sources: ManualSources
    language: str
    rule_seed: Literal[1]
    compiler_schema: str

    @property
    def fingerprint(self) -> str:
        """Return the deterministic identity of this definition."""
        return stable_digest(self.model_dump(mode="json"))


def _source_snapshot(profile: ManualProfile, sources: ManualSources) -> ManualSources:
    """Keep the source configuration selected by one profile."""
    if profile.include_frontmatter and not sources.frontmatter:
        raise ValueError("include_frontmatter is enabled but no frontmatter source is configured")

    frontmatter = sources.frontmatter if profile.include_frontmatter else ()
    documents = (*frontmatter, *profile.documents)
    official_languages = {
        document.language for document in documents if isinstance(document, OfficialDocument)
    }
    missing_languages = official_languages - sources.official_manual.keys()
    if missing_languages:
        raise ValueError(
            f"official manual sources are not configured for: {sorted(missing_languages)}"
        )
    official_manual = {
        language: sources.official_manual[language] for language in sorted(official_languages)
    }
    return sources.model_copy(
        update={"frontmatter": frontmatter, "official_manual": official_manual}
    )


def compose_manual_build_definition(
    *, profile: ManualProfile, language: str, rule_seed: Literal[1], compiler_schema: str
) -> ManualBuildDefinition:
    """Read the current source pins and build the definition stored by suite freeze."""
    sources = ManualSources.from_path(Paths().manual_sources)
    return ManualBuildDefinition(
        profile=profile,
        sources=_source_snapshot(profile, sources),
        language=language,
        rule_seed=rule_seed,
        compiler_schema=compiler_schema,
    )
