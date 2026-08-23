from pathlib import Path
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from gptnt.common.hashing import stable_digest

type DocumentName = Annotated[str, Field(pattern=r"^[^/\\]+\.html$")]
"""The name of one HTML document in the KtaneContent repository, without any directory."""


def _require_html_suffix(path: Path) -> Path:
    if path.suffix != ".html":
        raise ValueError("a local document must be an .html file")
    return path


type LocalHtmlPath = Annotated[Path, AfterValidator(_require_html_suffix)]
"""A path to a local HTML file.

Directories are allowed, and we do not care what it is relative to.
"""


class OfficialDocument(BaseModel):
    """A page taken from the official bombmanual.com manual for a language."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: Literal["official"]

    id: str
    """ModuleID for the component.

    This still matters even though the page is extracted from the official PDF.
    """

    language: str
    """Language of the official manual.

    The official manual is only available in one language at a time, and that language must match
    the game being played. That match is checked at resolve time against the mission, not here.
    """


class KtaneContentDocument(BaseModel):
    """A module document from KtaneContent, resolved by id and language."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: Literal["ktanecontent"]

    id: str
    """ModuleID for the component."""

    language: str
    """Language this document is written in.

    If provided, we attempt to resolve this against the repository, and if it's not found, it'll
    error.
    """

    document: DocumentName | None = None
    """A specific page to use INSTEAD OF the module's default document for this language.

    This is the name of the HTML file in the repository. If not provided, we resolve the default
    document for the chosen language.
    """


class KtaneContentAppendix(BaseModel):
    """An appendix document from KtaneContent that does not have a ModuleID."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: Literal["ktanecontent"]

    language: str
    """Language this appendix is written in."""

    document: DocumentName
    """Document name.

    This is the only way to identify an appendix since it does not have a ModuleID. It must be a
    single HTML file in the repository.
    """


class LocalDocument(BaseModel):
    """A document supplied from a local file, outside the pinned sources."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: Literal["local"]

    path: LocalHtmlPath
    """Path to the local HTML file.

    Directories are allowed, unlike a repository document name.
    """

    language: str
    """Language this document is written in."""

    id: str | None = None
    """ModuleID this document stands in for, when it replaces a module's page."""


type Document = OfficialDocument | KtaneContentDocument | KtaneContentAppendix | LocalDocument
"""A document (module, widget, appendix, etc.) used in the manual."""


class ManualProfile(BaseModel):
    """The documents a manual contains and the order they appear in."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    include_frontmatter: bool
    """Whether to include the frontmatter pages in the manual."""

    documents: tuple[Document, ...] = Field(min_length=1)
    """Documents to include, in what order they need to appear."""

    @property
    def runtime_digest(self) -> str:
        """Return the stable digest used to address this profile at runtime."""
        return stable_digest(self.model_dump(mode="json"))
