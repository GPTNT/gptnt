"""Resolve manual profiles into ordered source inputs without rendering their contents."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from gptnt.ktane.manuals import _assets, _ktane_content
from gptnt.ktane.manuals.profile import (
    Document,
    KtaneContentAppendix,
    KtaneContentDocument,
    LocalDocument,
    ManualProfile,
    OfficialDocument,
)
from gptnt.ktane.manuals.resolution import (
    KtaneContentModuleMetadata,
    KtaneContentProvenance,
    LocalInputIdentity,
    LocalProvenance,
    OfficialManualProvenance,
    ResolvedDocument,
    ResolvedKtaneContentAppendix,
    ResolvedKtaneContentModule,
    ResolvedLocalDocument,
    ResolvedOfficialDocument,
)

if TYPE_CHECKING:
    from pathlib import Path

    from gptnt.ktane.manuals.sources import ManualSources

__all__ = ["ManualResolutionError", "resolve_manual_profile"]

_DEFAULT_RULE_SEED = 1


class ManualResolutionError(ValueError):
    """A profile entry cannot be represented by the configured and cached sources."""


def _entry_name(document: Document, *, index: int, frontmatter: bool) -> str:
    collection = "frontmatter" if frontmatter else "documents"
    if isinstance(document, KtaneContentAppendix):
        identity = document.document
    elif isinstance(document, LocalDocument):
        identity = document.id or document.path.as_posix()
    else:
        identity = document.id
    return f"{collection}[{index}] ({document.source}:{identity})"


def _cached_catalog(cache_dir: Path, *, entry_name: str) -> _ktane_content.KtaneContentCatalog:
    path = cache_dir / "sources" / "ktanecontent" / "catalog" / "raw.json"
    if not path.is_file():
        raise ManualResolutionError(
            f"{entry_name}: cached KtaneContent catalog is missing at {path}"
        )
    try:
        return _ktane_content.KtaneContentCatalog.from_path(path)
    except (OSError, ValueError) as error:
        raise ManualResolutionError(
            f"{entry_name}: cached KtaneContent catalog at {path} is invalid"
        ) from error


def _catalog_filename(
    catalog: _ktane_content.KtaneContentCatalog,
    document: KtaneContentDocument | KtaneContentAppendix,
    *,
    entry_name: str,
) -> str:
    try:
        return catalog.filename_for(document)
    except ValueError as error:
        raise ManualResolutionError(f"{entry_name}: {error}") from error


def _require_source_file(path: Path, *, entry_name: str, description: str) -> None:
    if not path.is_file():
        raise ManualResolutionError(
            f"{entry_name}: {description} is missing from the pinned source tree"
        )


def _ktane_metadata(
    catalog: _ktane_content.KtaneContentCatalog,
    document: KtaneContentDocument,
    *,
    repository_dir: Path,
    entry_name: str,
) -> tuple[str, Path, KtaneContentModuleMetadata]:
    try:
        metadata_document = catalog.metadata_filename_for(document)
    except ValueError as error:
        raise ManualResolutionError(f"{entry_name}: {error}") from error
    metadata_path = repository_dir / "JSON" / metadata_document
    _require_source_file(
        metadata_path,
        entry_name=entry_name,
        description=f"KtaneContent metadata {metadata_document!r}",
    )
    try:
        metadata = KtaneContentModuleMetadata.from_path(metadata_path)
    except (OSError, ValueError) as error:
        raise ManualResolutionError(
            f"{entry_name}: KtaneContent metadata {metadata_document!r} is invalid"
        ) from error
    if metadata.module_id != document.id:
        raise ManualResolutionError(
            f"{entry_name}: KtaneContent metadata identifies module {metadata.module_id!r}, "
            f"not {document.id!r}"
        )
    return metadata_document, metadata_path, metadata


def _resolve_ktane_content(
    document: KtaneContentDocument | KtaneContentAppendix,
    *,
    sources: ManualSources,
    cache_dir: Path,
    entry_name: str,
) -> ResolvedKtaneContentModule | ResolvedKtaneContentAppendix:
    catalog = _cached_catalog(cache_dir, entry_name=entry_name)
    filename = _catalog_filename(catalog, document, entry_name=entry_name)
    repository_dir = cache_dir / "sources" / "ktanecontent" / sources.ktane_content.commit
    source_path = repository_dir / "HTML" / filename
    _require_source_file(
        source_path, entry_name=entry_name, description=f"KtaneContent document {filename!r}"
    )

    if isinstance(document, KtaneContentAppendix):
        return ResolvedKtaneContentAppendix(
            logical_id=document.document,
            language=document.language,
            source="ktanecontent",
            source_path=source_path,
            provenance=KtaneContentProvenance(
                commit=sources.ktane_content.commit, document=filename
            ),
            can_represent_rule_seed=True,
        )

    metadata_document, metadata_path, metadata = _ktane_metadata(
        catalog, document, repository_dir=repository_dir, entry_name=entry_name
    )
    return ResolvedKtaneContentModule(
        logical_id=document.id,
        language=document.language,
        source="ktanecontent",
        source_path=source_path,
        metadata_path=metadata_path,
        metadata=metadata,
        provenance=KtaneContentProvenance(
            commit=sources.ktane_content.commit,
            document=filename,
            metadata_document=metadata_document,
        ),
        can_represent_rule_seed=True,
    )


def _resolve_official(
    document: OfficialDocument, *, sources: ManualSources, cache_dir: Path, entry_name: str
) -> ResolvedOfficialDocument:
    source = sources.official_manual.get(document.language)
    if source is None:
        raise ManualResolutionError(
            f"{entry_name}: official manual source is not configured for language {document.language!r}"
        )
    page_range = source.pages.get(document.id)
    if page_range is None:
        raise ManualResolutionError(
            f"{entry_name}: official manual {document.language!r} has no page map for {document.id!r}"
        )
    source_path = source.cache_path(document.language, cache_dir=cache_dir)
    if not source_path.is_file():
        raise ManualResolutionError(
            f"{entry_name}: cached official manual is missing at {source_path}"
        )
    return ResolvedOfficialDocument(
        logical_id=document.id,
        language=document.language,
        source="official",
        source_path=source_path,
        page_range=page_range,
        provenance=OfficialManualProvenance(version=source.version, url=str(source.url)),
        can_represent_rule_seed=True,
    )


def _local_references(source: Path, *, root_dir: Path, entry_name: str) -> set[Path]:
    try:
        references = _assets.extract_references_from_file(source)
    except (OSError, UnicodeError) as error:
        raise ManualResolutionError(
            f"{entry_name}: local input {source} cannot be read for dependency discovery"
        ) from error

    dependencies: set[Path] = set()
    for reference in references:
        dependency = _assets.resolve_local_reference(source, reference, root_dir=root_dir)
        if dependency is None:
            continue
        if not dependency.is_file():
            raise ManualResolutionError(
                f"{entry_name}: local dependency {dependency} referenced by {source} is missing"
            )
        dependencies.add(dependency)
    return dependencies


def _local_dependencies(source_path: Path, *, root_dir: Path, entry_name: str) -> set[Path]:
    selected = {source_path}
    pending = {source_path}
    while pending:
        source = pending.pop()
        discovered = _local_references(source, root_dir=root_dir, entry_name=entry_name)
        pending.update(discovered - selected)
        selected.update(discovered)
    return selected


def _local_input_path(path: Path, *, root_dir: Path) -> str:
    try:
        return path.relative_to(root_dir.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _resolve_local(
    document: LocalDocument, *, root_dir: Path, entry_name: str
) -> ResolvedLocalDocument:
    source_path = document.path if document.path.is_absolute() else root_dir / document.path
    source_path = source_path.resolve()
    if not source_path.is_file():
        raise ManualResolutionError(f"{entry_name}: local HTML source is missing at {source_path}")
    inputs: list[LocalInputIdentity] = []
    for path in sorted(
        _local_dependencies(source_path, root_dir=root_dir, entry_name=entry_name),
        key=lambda dependency: dependency.as_posix(),
    ):
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as error:
            raise ManualResolutionError(
                f"{entry_name}: local input {path} cannot be read for source identity"
            ) from error
        inputs.append(
            LocalInputIdentity(path=_local_input_path(path, root_dir=root_dir), sha256=digest)
        )
    return ResolvedLocalDocument(
        logical_id=document.id or document.path.name,
        language=document.language,
        source="local",
        source_path=source_path,
        provenance=LocalProvenance(inputs=tuple(inputs)),
        can_represent_rule_seed=True,
    )


def _resolve_document(
    document: Document, *, sources: ManualSources, cache_dir: Path, root_dir: Path, entry_name: str
) -> ResolvedDocument:
    if isinstance(document, (KtaneContentDocument, KtaneContentAppendix)):
        return _resolve_ktane_content(
            document, sources=sources, cache_dir=cache_dir, entry_name=entry_name
        )
    if isinstance(document, OfficialDocument):
        return _resolve_official(
            document, sources=sources, cache_dir=cache_dir, entry_name=entry_name
        )
    return _resolve_local(document, root_dir=root_dir, entry_name=entry_name)


def resolve_manual_profile(
    profile: ManualProfile,
    *,
    sources: ManualSources,
    cache_dir: Path,
    root_dir: Path,
    language: str,
    rule_seed: int,
) -> tuple[ResolvedDocument, ...]:
    """Return frontmatter followed by profile documents as ordered compilation inputs.

    Every entry is checked against the requested language, default rule seed, configured source
    metadata, and materialized local inputs before the tuple is returned. Failures name the
    frontmatter or profile index whose source, page map, file, or dependency cannot be resolved.
    The function reads HTML, JSON, and PDF inputs but does not render or compile them.
    """
    configured: list[tuple[Document, int, bool]] = []
    if profile.include_frontmatter:
        if not sources.frontmatter:
            raise ManualResolutionError(
                "frontmatter: include_frontmatter is enabled but no frontmatter source is configured"
            )
        configured.extend(
            (document, index, True) for index, document in enumerate(sources.frontmatter)
        )
    configured.extend((document, index, False) for index, document in enumerate(profile.documents))

    first_document, first_index, first_is_frontmatter = configured[0]
    if rule_seed != _DEFAULT_RULE_SEED:
        entry_name = _entry_name(
            first_document, index=first_index, frontmatter=first_is_frontmatter
        )
        raise ManualResolutionError(
            f"{entry_name}: rule seed {rule_seed} is unsupported; "
            f"only default rule seed {_DEFAULT_RULE_SEED} can be resolved"
        )

    resolved: list[ResolvedDocument] = []
    for document, index, is_frontmatter in configured:
        entry_name = _entry_name(document, index=index, frontmatter=is_frontmatter)
        if document.language != language:
            raise ManualResolutionError(
                f"{entry_name}: document language {document.language!r} does not match "
                f"requested language {language!r}"
            )
        resolved.append(
            _resolve_document(
                document,
                sources=sources,
                cache_dir=cache_dir,
                root_dir=root_dir,
                entry_name=entry_name,
            )
        )
    return tuple(resolved)
