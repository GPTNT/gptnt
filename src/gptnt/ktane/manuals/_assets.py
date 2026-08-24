"""Find the KtaneContent files needed by the selected manual documents.

We use a blobless Git clone because we do not want to download the whole KtaneContent website just
to build a manual. Restoring only the selected HTML files is not enough, though. Those files still
need their stylesheets, images and scripts, and those files can have dependencies of their own.

This is deliberately a static scanner. It handles the ordinary ways HTML, CSS, JavaScript and SVG
files refer to other files. It does not attempt to run JavaScript or guess paths assembled at
runtime.
"""

import posixpath
import re
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import ClassVar, override
from urllib.parse import unquote, urlsplit

_CSS_URL = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", flags=re.IGNORECASE)
_CSS_IMPORT = re.compile(r"@import\s+(?:url\(\s*)?['\"]([^'\"]+)['\"]", flags=re.IGNORECASE)
_JS_IMPORT_FROM = re.compile(
    r"\b(?:import|export)\s+[^;]*?\s+from\s*['\"]([^'\"]+)['\"]", flags=re.IGNORECASE
)
_JS_BARE_IMPORT = re.compile(r"\bimport\s*['\"]([^'\"]+)['\"]", flags=re.IGNORECASE)
_JS_DYNAMIC_IMPORT = re.compile(r"\bimport\s*\(\s*['\"]([^'\"]+)['\"]\s*\)", flags=re.IGNORECASE)
_XML_REFERENCE = re.compile(r"(?:href|xlink:href)=['\"]([^'\"]+)['\"]", flags=re.IGNORECASE)


def _css_references(text: str) -> set[str]:
    """Return local URL references from one CSS stylesheet or embedded rule block."""
    return {match[1] for match in _CSS_URL.findall(text)} | set(_CSS_IMPORT.findall(text))


class _HtmlAssetParser(HTMLParser):
    """Collect file-bearing attributes from HTML start tags.

    The mapping is explicit so attributes such as a link's `href` are included while unrelated
    attributes are ignored. `srcset` needs separate handling because one attribute can contain
    several candidates, optionally followed by width or pixel-density descriptors.
    """

    _attributes: ClassVar[dict[str, tuple[str, ...]]] = {
        "embed": ("src",),
        "iframe": ("src",),
        "img": ("src", "srcset"),
        "input": ("src",),
        "link": ("href",),
        "object": ("data",),
        "script": ("src",),
        "source": ("src", "srcset"),
        "video": ("poster", "src"),
    }

    def __init__(self) -> None:
        super().__init__()
        self.references: set[str] = set()
        self._in_style = False

    @override
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "style":
            self._in_style = True
        selected = self._attributes.get(tag, ())
        for name, attribute_value in attrs:
            if attribute_value is None or name not in selected:
                continue
            if name == "srcset":
                self.references.update(
                    candidate.split()[0]
                    for candidate in attribute_value.split(",")
                    if candidate.split()
                )
            else:
                self.references.add(attribute_value)

    @override
    def handle_endtag(self, tag: str) -> None:
        if tag == "style":
            self._in_style = False

    @override
    def handle_data(self, data: str) -> None:
        if self._in_style:
            self.references.update(_css_references(data))


def extract_references_from_file(path: Path) -> set[str]:
    """Return the resource references written in one supported repository file.

    HTML uses a small `HTMLParser` because its attributes are structured. CSS, JavaScript and SVG
    only need the limited reference forms used by KtaneContent, so we can use regex to keep that
    simple. Binary assets and file types that cannot lead us to another dependency return an
    empty set.

    The values can be URLs or filesystem paths. Both forms can use URL escaping. Resolving and
    checking them is a separate step.
    """
    suffix = path.suffix.lower()
    if suffix not in {".css", ".html", ".js", ".svg"}:
        return set()
    text = path.read_text(encoding="utf-8")
    if suffix == ".html":
        parser = _HtmlAssetParser()
        parser.feed(text)
        return parser.references
    if suffix == ".css":
        return _css_references(text)
    if suffix == ".js":
        return (
            set(_JS_IMPORT_FROM.findall(text))
            | set(_JS_BARE_IMPORT.findall(text))
            | set(_JS_DYNAMIC_IMPORT.findall(text))
        )
    return set(_XML_REFERENCE.findall(text)) | {match[1] for match in _CSS_URL.findall(text)}


def _resolve(source: str, *, reference: str) -> str | None:
    """Turn a URL-like reference into a normalized repository-relative path.

    `source` is already relative to the repository root. A reference beginning with `/` is
    treated as relative to that root; every other local reference is relative to the source file's
    directory. External URLs and references without a path do not identify a file we need from Git,
    so they return `None`.
    """
    parsed = urlsplit(reference.strip())
    if parsed.scheme or parsed.netloc or not parsed.path:
        return None
    decoded = unquote(parsed.path)
    if decoded.startswith("/"):
        candidate = decoded.lstrip("/")
    else:
        candidate = posixpath.join(str(PurePosixPath(source).parent), decoded)
    normalized = posixpath.normpath(candidate)
    if normalized == ".." or normalized.startswith("../"):
        raise ValueError(
            f"asset reference {reference!r} from {source!r} escapes the source repository"
        )
    return normalized


def resolve_repository_reference(
    source: str, reference: str, *, repository_paths: set[str]
) -> str | None:
    """Resolve one reference and require its target to exist in the pinned Git tree.

    Returning `None` means the reference is not a local repository file and can be ignored.
    Returning a string gives the downloader an exact path to restore. A missing local path raises
    here instead of being silently omitted, because otherwise the cached manual would be incomplete
    and the failure would only appear later when it is built or opened.
    """
    resolved = _resolve(source, reference=reference)
    if resolved is None or resolved in repository_paths:
        return resolved

    # The pinned HTML/css/font.css says its fonts are in HTML/css/fonts, while the repository keeps
    # them in HTML/font. Correct that one known upstream mistake here. Applying this to every
    # stylesheet would hide other broken paths, so the source file and broken prefix are both
    # checked before accepting the corrected path.
    broken_font_prefix = "HTML/css/fonts/"
    if source == "HTML/css/font.css" and resolved.startswith(broken_font_prefix):
        corrected = f"HTML/font/{resolved.removeprefix(broken_font_prefix)}"
        if corrected in repository_paths:
            return corrected

    raise ValueError(f"KtaneContent asset {resolved!r}, referenced by {source!r}, does not exist")


def resolve_local_reference(source: Path, reference: str, *, root_dir: Path) -> Path | None:
    """Resolve one local document reference against its file or configured source root.

    External and fragment-only references return `None`. Website-absolute paths start at
    `root_dir` and cannot leave it after URL decoding and path normalization; other paths start
    beside `source`. Existence is checked by the caller so it can name the profile entry that
    introduced a missing dependency.
    """
    parsed = urlsplit(reference.strip())
    if parsed.scheme or parsed.netloc or not parsed.path:
        return None
    decoded = unquote(parsed.path)
    if decoded.startswith("/"):
        # A leading slash selects the configured website root, not the host filesystem root. Keep
        # decoded parent segments and symlinks from turning that syntax into access outside it.
        resolved_root = root_dir.resolve()
        dependency = (resolved_root / decoded.lstrip("/")).resolve()
        if not dependency.is_relative_to(resolved_root):
            raise ValueError(
                f"local asset reference {reference!r} from {source} "
                "escapes the configured source root"
            )
        return dependency
    return (source.parent / decoded).resolve()
