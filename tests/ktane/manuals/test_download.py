"""Manual download selection, recursive asset discovery, and cache-reuse behavior."""

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
import pytest
import respx

from gptnt.ktane.manuals import _assets
from gptnt.ktane.manuals.download import download_manual_assets
from gptnt.ktane.manuals.profile import (
    KtaneContentDocument,
    LocalDocument,
    ManualProfile,
    OfficialDocument,
)
from gptnt.ktane.manuals.resolution import ResolvedKtaneContentModule
from gptnt.ktane.manuals.resolve import resolve_manual_profile
from gptnt.ktane.manuals.sources import (
    KtaneContentCatalogSource,
    KtaneContentSource,
    ManualSources,
    OfficialManualSource,
)

if TYPE_CHECKING:
    from gptnt.ktane.manuals.progress import DownloadProgress

# The aggregate catalog only needs the fields used to map a profile's module ID to Wires.html.
CATALOG = b'{"KtaneModules":[{"ModuleID":"Wires","Name":"Wires"}]}'
DUMMY_COMMIT = "0" * 40


def _write(path: Path, content: str | bytes) -> None:
    """Write one text or binary file while constructing a temporary source repository."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, str):
        _ = path.write_text(content, encoding="utf-8")
    else:
        _ = path.write_bytes(content)


def _source_repository(tmp_path: Path) -> tuple[Path, str]:
    """Create a small Git repository with recursive assets and one unrelated document."""
    repository = tmp_path / "upstream"
    repository.mkdir()

    # Wires.html references CSS and an image; the CSS then references a font. This gives the
    # downloader two layers of references to discover without reproducing KtaneContent itself.
    _write(
        repository / "HTML" / "Wires.html",
        '<link rel="stylesheet" href="css/main.css"><img src="img/Wires.svg">',
    )
    _write(repository / "HTML" / "css" / "main.css", "url('../font/manual.woff2')")
    _write(repository / "HTML" / "font" / "manual.woff2", b"font")
    _write(repository / "HTML" / "img" / "Wires.svg", "<svg></svg>")
    _write(
        repository / "JSON" / "Wires.json",
        '{"ModuleID":"Wires","Name":"Wires","Origin":"Vanilla",'
        '"SortKey":"WIRES","RuleSeedSupport":"Supported"}',
    )
    _write(repository / "HTML" / "Wires Override.html", "override")

    # The downloader can see this path in the Git tree but must not materialize it into the cache.
    _write(repository / "HTML" / "Unrelated.html", "unused")

    # A commit is required because production restores selected paths from a pinned revision.
    _ = subprocess.run(["git", "init", "--quiet"], cwd=repository, check=True)
    _ = subprocess.run(["git", "add", "."], cwd=repository, check=True)
    _ = subprocess.run(
        [
            "git",
            "-c",
            "user.name=GPTNT Tests",
            "-c",
            "user.email=tests@gptnt.invalid",
            "commit",
            "--quiet",
            "-m",
            "fixture",
        ],
        cwd=repository,
        check=True,
    )
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repository, check=True, capture_output=True, text=True
    )
    return repository, revision.stdout.strip()


def _sources(
    repository: Path | None = None, commit: str = DUMMY_COMMIT, *, include_official: bool = True
) -> ManualSources:
    """Build source configuration with only the upstreams needed by downloader tests."""
    repository_url = (
        "https://unused.test/content.git" if repository is None else f"file://{repository}"
    )
    official_manual = {
        "fr": OfficialManualSource(version="1-fr", url="https://manual.test/fr.pdf")
    }
    return ManualSources(
        ktane_content=KtaneContentSource(
            repository=repository_url,
            commit=commit,
            catalog=KtaneContentCatalogSource(url="https://catalog.test/raw"),
        ),
        official_manual=official_manual if include_official else {},
    )


def _ktane_content_profile() -> ManualProfile:
    return ManualProfile(
        include_frontmatter=False,
        documents=(KtaneContentDocument(source="ktanecontent", id="Wires", language="en"),),
    )


def _official_profile() -> ManualProfile:
    """Select two modules from the same official manual language."""
    return ManualProfile(
        include_frontmatter=False,
        documents=(
            OfficialDocument(source="official", id="Wires", language="fr"),
            OfficialDocument(source="official", id="BigButton", language="fr"),
        ),
    )


@pytest.mark.anyio
async def test_download_caches_selected_ktanecontent_files_and_recursive_references(
    tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    """Download only the selected page and its recursively referenced repository files."""
    repository, commit = _source_repository(tmp_path)
    catalog_route = respx_mock.get("https://catalog.test/raw").mock(
        return_value=httpx.Response(
            200, content=CATALOG, headers={"Content-Length": str(len(CATALOG))}
        )
    )
    updates: list[DownloadProgress] = []

    cache_dir = tmp_path / "cache"
    async with httpx.AsyncClient() as client:
        # The first run downloads the catalog and restores the selected repository files.
        added = await download_manual_assets(
            [_ktane_content_profile()],
            sources=_sources(repository, commit),
            cache_dir=cache_dir,
            root_dir=tmp_path,
            progress=updates.append,
            client=client,
        )

        # The second run must reuse both the catalog and every already-materialized asset.
        cached = await download_manual_assets(
            [_ktane_content_profile()],
            sources=_sources(repository, commit),
            cache_dir=cache_dir,
            root_dir=tmp_path,
            client=client,
        )

    # Exact file membership proves recursive references were included and Unrelated.html was not.
    revision = cache_dir / "sources" / "ktanecontent" / commit
    cached_files = {
        path.relative_to(revision).as_posix()
        for path in revision.rglob("*")
        if path.is_file() and ".git" not in path.relative_to(revision).parts
    }
    assert cached_files == {
        "HTML/Wires.html",
        "HTML/css/main.css",
        "HTML/font/manual.woff2",
        "HTML/img/Wires.svg",
        "JSON/Wires.json",
    }
    # The catalog is requested once; the local Git remote supplies only the selected blobs.
    assert catalog_route.call_count == 1
    assert (added.added_files, added.cached_files) == (6, 0)
    assert (cached.added_files, cached.cached_files) == (0, 6)
    assert any(
        update.description == "Selected KtaneContent assets are cached"
        and update.completed == update.total == 5
        for update in updates
    )


@pytest.mark.anyio
async def test_downloader_and_resolver_share_ktanecontent_filename_selection(
    tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    """Use an explicit override instead of the catalog default in both stages."""
    repository, commit = _source_repository(tmp_path)
    _ = respx_mock.get("https://catalog.test/raw").mock(
        return_value=httpx.Response(200, content=CATALOG)
    )
    profile = ManualProfile(
        include_frontmatter=False,
        documents=(
            KtaneContentDocument(
                source="ktanecontent", id="Wires", language="en", document="Wires Override.html"
            ),
        ),
    )
    sources = _sources(repository, commit)
    cache_dir = tmp_path / "cache"

    async with httpx.AsyncClient() as client:
        _ = await download_manual_assets(
            [profile], sources=sources, cache_dir=cache_dir, root_dir=tmp_path, client=client
        )
    resolved = resolve_manual_profile(
        profile,
        sources=sources,
        cache_dir=cache_dir,
        root_dir=tmp_path,
        language="en",
        rule_seed=1,
    )

    assert len(resolved) == 1
    document = resolved[0]
    assert isinstance(document, ResolvedKtaneContentModule)
    assert document.source_path.name == "Wires Override.html"


@pytest.mark.anyio
async def test_download_fetches_one_official_manual_per_language_and_reuses_it(
    tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    """Share one cached official PDF among every selected module in its language."""
    manual = b"configured PDF response"
    manual_route = respx_mock.get("https://manual.test/fr.pdf").mock(
        return_value=httpx.Response(
            200, content=manual, headers={"Content-Length": str(len(manual))}
        )
    )
    updates: list[DownloadProgress] = []

    cache_dir = tmp_path / "cache"
    async with httpx.AsyncClient() as client:
        added = await download_manual_assets(
            [_official_profile()],
            sources=_sources(),
            cache_dir=cache_dir,
            root_dir=tmp_path,
            progress=updates.append,
            client=client,
        )
        cached = await download_manual_assets(
            [_official_profile()],
            sources=_sources(),
            cache_dir=cache_dir,
            root_dir=tmp_path,
            client=client,
        )

    # Both profile entries use French, so they share one cached official PDF.
    assert manual_route.call_count == 1
    assert (added.added_files, added.cached_files) == (1, 0)
    assert (cached.added_files, cached.cached_files) == (0, 1)
    assert updates[0].completed == 0
    assert updates[-1].completed == updates[-1].total == len(manual)


def test_javascript_dependencies_include_only_literal_imports(tmp_path: Path) -> None:
    """Extract literal JavaScript imports without treating ordinary strings as dependencies."""
    script = tmp_path / "module.js"
    _write(
        script,
        'import "./helper.js"; export {value} from "./other.js"; '
        'import("./lazy.js"); return "No conversion from "+u+" to "+o;',
    )

    # The final string resembles minified JavaScript seen upstream but is not an import.
    assert _assets.extract_references_from_file(script) == {
        "./helper.js",
        "./other.js",
        "./lazy.js",
    }


def test_broken_font_stylesheet_reference_uses_existing_font() -> None:
    """Correct the known font.css path error without correcting unrelated missing paths."""
    repository_paths = {"HTML/font/Alef-Regular.ttf"}

    # KtaneContent's font.css contains a known fonts/ path error. The correction is deliberately
    # limited to that stylesheet so an equivalent missing path elsewhere still raises.
    assert (
        _assets.resolve_repository_reference(
            "HTML/css/font.css", "fonts/Alef-Regular.ttf", repository_paths=repository_paths
        )
        == "HTML/font/Alef-Regular.ttf"
    )
    with pytest.raises(ValueError, match="does not exist"):
        _ = _assets.resolve_repository_reference(
            "HTML/css/main.css", "fonts/Alef-Regular.ttf", repository_paths=repository_paths
        )


@pytest.mark.anyio
async def test_missing_official_language_is_rejected_before_creating_cache(tmp_path: Path) -> None:
    """Reject an unconfigured official language before creating cache state."""
    # Source/profile mismatches must fail during planning, before creating cache directories.
    with pytest.raises(ValueError, match="not configured for"):
        _ = await download_manual_assets(
            [_official_profile()],
            sources=_sources(include_official=False),
            cache_dir=tmp_path / "cache",
            root_dir=tmp_path,
        )

    assert not tmp_path.joinpath("cache").exists()


@pytest.mark.anyio
async def test_local_document_requires_no_download_or_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Validate an existing local document without starting HTTP or creating a cache."""
    document = tmp_path / "notes" / "Wires.html"
    _write(document, "local notes")
    profile = ManualProfile(
        include_frontmatter=False,
        documents=(LocalDocument(source="local", path=document, language="en"),),
    )
    monkeypatch.setattr(
        "gptnt.ktane.manuals.download.cached_retrying_async_http_client",
        lambda **_kwargs: pytest.fail("local documents must not create an HTTP client"),
    )

    # Local documents are validated in place; the download command neither copies nor counts them.
    download = await download_manual_assets(
        [profile], sources=_sources(), cache_dir=tmp_path / "cache", root_dir=tmp_path
    )

    assert (download.added_files, download.cached_files) == (0, 0)
    assert not tmp_path.joinpath("cache").exists()


@pytest.mark.anyio
async def test_missing_local_document_is_rejected(tmp_path: Path) -> None:
    """Reject a missing local document during download planning."""
    profile = ManualProfile(
        include_frontmatter=False,
        documents=(LocalDocument(source="local", path=Path("missing.html"), language="en"),),
    )

    with pytest.raises(ValueError, match="local manual document does not exist"):
        _ = await download_manual_assets(
            [profile], sources=_sources(), cache_dir=tmp_path / "cache", root_dir=tmp_path
        )
