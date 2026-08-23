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

_DEFAULT_RULE_SEED = 1


def _entry_name(document: Document, *, index: int, frontmatter: bool) -> str:
    """Build the profile location and source identity used in resolution errors."""
    collection = "frontmatter" if frontmatter else "documents"
    if isinstance(document, KtaneContentAppendix):
        identity = document.document
    elif isinstance(document, LocalDocument):
        identity = document.id or document.path.as_posix()
    else:
        identity = document.id
    return f"{collection}[{index}] ({document.source}:{identity})"


def _module_metadata(
    catalog: _ktane_content.KtaneContentCatalog,
    document: KtaneContentDocument,
    *,
    repository_dir: Path,
    entry_name: str,
) -> tuple[str, Path, KtaneContentModuleMetadata]:
    """Load the canonical JSON metadata for one KtaneContent module.

    The metadata name is independent of a translated or overridden HTML filename. Missing metadata
    and an incorrect module ID are expected source mismatches; malformed JSON retains its parser
    exception.
    """
    metadata_document = f"{catalog.module_names[document.id]}.json"
    metadata_path = repository_dir / "JSON" / metadata_document
    if not metadata_path.is_file():
        raise ValueError(
            f"{entry_name}: KtaneContent metadata {metadata_document!r} "
            "is missing from the pinned source tree"
        )

    metadata = KtaneContentModuleMetadata.model_validate_json(metadata_path.read_bytes())
    if metadata.module_id != document.id:
        raise ValueError(
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
    """Resolve one KtaneContent profile entry from the pinned source cache.

    Appendix entries need only their explicitly selected HTML file. Module entries also load the
    canonical JSON metadata used by later compiler stages.
    """
    # Load the catalog written by the downloader. Invalid JSON is unexpected cache corruption, so
    # its parser exception is left intact.
    catalog_path = cache_dir / "sources" / "ktanecontent" / "catalog" / "raw.json"
    if not catalog_path.is_file():
        raise ValueError(f"{entry_name}: cached KtaneContent catalog is missing at {catalog_path}")
    catalog = _ktane_content.KtaneContentCatalog.from_path(catalog_path)

    # Resolve the requested HTML name. Catalog lookup and language-policy exceptions retain their
    # native types and messages.
    filename = catalog.filename_for(document)

    # Both the resolver and downloader address files under the pinned commit directory.
    repository_dir = cache_dir / "sources" / "ktanecontent" / sources.ktane_content.commit
    source_path = repository_dir / "HTML" / filename
    if not source_path.is_file():
        raise ValueError(
            f"{entry_name}: KtaneContent document {filename!r} is missing from the pinned source tree"
        )

    if isinstance(document, KtaneContentAppendix):
        return ResolvedKtaneContentAppendix(
            document_id=document.document,
            language=document.language,
            source="ktanecontent",
            source_path=source_path,
            provenance=KtaneContentProvenance(
                commit=sources.ktane_content.commit, document=filename
            ),
            supports_requested_rule_seed=True,
        )

    metadata_document, metadata_path, metadata = _module_metadata(
        catalog, document, repository_dir=repository_dir, entry_name=entry_name
    )
    return ResolvedKtaneContentModule(
        document_id=document.id,
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
        supports_requested_rule_seed=True,
    )


def _resolve_official(
    document: OfficialDocument, *, sources: ManualSources, cache_dir: Path, entry_name: str
) -> ResolvedOfficialDocument:
    """Resolve one document to its configured pages in a cached official PDF.

    Language availability and page intervals belong to source configuration. The PDF must already
    occupy the cache path shared with the downloader.
    """
    # Select the language-specific PDF and the pages assigned to this document ID.
    source = sources.official_manual.get(document.language)
    if source is None:
        raise ValueError(
            f"{entry_name}: official manual source is not configured for language {document.language!r}"
        )

    page_range = source.pages.get(document.id)
    if page_range is None:
        raise ValueError(
            f"{entry_name}: official manual {document.language!r} has no page map for {document.id!r}"
        )

    # The downloader and resolver share this path. Resolution never fetches the PDF itself.
    source_path = source.cache_path(document.language, cache_dir=cache_dir)
    if not source_path.is_file():
        raise ValueError(f"{entry_name}: cached official manual is missing at {source_path}")

    return ResolvedOfficialDocument(
        document_id=document.id,
        language=document.language,
        source="official",
        source_path=source_path,
        page_range=page_range,
        provenance=OfficialManualProvenance(version=source.version, url=str(source.url)),
        supports_requested_rule_seed=True,
    )


def _direct_local_dependencies(source: Path, *, root_dir: Path, entry_name: str) -> set[Path]:
    """Resolve the existing local files referenced directly by one input.

    External URLs and fragment-only references are ignored. A local reference is an expected
    profile input, so a missing file is reported against the profile entry.
    """
    dependencies: set[Path] = set()
    references = _assets.extract_references_from_file(source)

    # Resolve references as one block so path-boundary errors gain profile context without adding
    # exception handling to each loop iteration.
    try:
        for reference in references:
            dependency = _assets.resolve_local_reference(source, reference, root_dir=root_dir)
            if dependency is not None:
                dependencies.add(dependency)
    except ValueError as error:
        raise ValueError(f"{entry_name}: {error}") from error

    # Missing resolved files are a separate profile-policy failure from references that leave the
    # configured source root.
    for dependency in dependencies:
        if not dependency.is_file():
            raise ValueError(
                f"{entry_name}: local dependency {dependency} referenced by {source} is missing"
            )

    return dependencies


def _local_dependencies(source_path: Path, *, root_dir: Path, entry_name: str) -> set[Path]:
    """Collect existing local dependencies, including the configured HTML file.

    File decoding and parsing errors retain their original exception types.
    """
    selected = {source_path}
    pending = {source_path}

    # Follow references until every reachable local file has been inspected. Only newly discovered
    # paths enter `pending`, so cycles do not reread a file.
    while pending:
        source = pending.pop()
        discovered = _direct_local_dependencies(source, root_dir=root_dir, entry_name=entry_name)
        pending.update(discovered - selected)
        selected.update(discovered)

    return selected


def _resolve_local(
    document: LocalDocument, *, root_dir: Path, entry_name: str
) -> ResolvedLocalDocument:
    """Resolve local HTML and derive a deterministic identity for its dependency graph.

    Each identity contains a stable path and SHA-256 digest. Any content change in the HTML or a
    referenced local file therefore changes the resolved provenance.
    """
    source_path = document.path if document.path.is_absolute() else root_dir / document.path
    source_path = source_path.resolve()
    if not source_path.is_file():
        raise ValueError(f"{entry_name}: local HTML source is missing at {source_path}")

    # Sort by absolute path so filesystem traversal order cannot alter the provenance tuple.
    dependencies = sorted(
        _local_dependencies(source_path, root_dir=root_dir, entry_name=entry_name),
        key=lambda dependency: dependency.as_posix(),
    )

    # Prefer configured-root-relative paths. An absolute configured input outside that root retains
    # its absolute path so the identity remains unambiguous.
    resolved_root = root_dir.resolve()
    inputs: list[LocalInputIdentity] = []
    for path in dependencies:
        try:
            identity_path = path.relative_to(resolved_root).as_posix()
        except ValueError:
            identity_path = path.as_posix()

        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        inputs.append(LocalInputIdentity(path=identity_path, sha256=digest))

    return ResolvedLocalDocument(
        document_id=document.id or document.path.name,
        language=document.language,
        source="local",
        source_path=source_path,
        provenance=LocalProvenance(inputs=tuple(inputs)),
        supports_requested_rule_seed=True,
    )


def _resolve_profile_entry(
    document: Document,
    *,
    sources: ManualSources,
    cache_dir: Path,
    root_dir: Path,
    language: str,
    entry_name: str,
) -> ResolvedDocument:
    """Apply shared language policy, then resolve one entry from its source."""
    # Validate language before accessing source configuration or cache paths so the error names the
    # profile entry that introduced the mismatch.
    if document.language != language:
        raise ValueError(
            f"{entry_name}: document language {document.language!r} does not match "
            f"requested language {language!r}"
        )

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

    Entries are checked against the requested language, default rule seed, configured source
    metadata, and materialized local inputs before the tuple is returned. `ValueError`
    conditions name the responsible frontmatter or profile index. Catalog lookups and malformed or
    unreadable source files retain their native exceptions. The function reads catalogs, module
    metadata, and local dependencies and checks the selected HTML and PDF paths. It does not render
    or compile them.
    """
    # Frontmatter precedes profile documents in the same order as its source configuration.
    configured: list[tuple[Document, int, bool]] = []
    if profile.include_frontmatter:
        if not sources.frontmatter:
            raise ValueError(
                "frontmatter: include_frontmatter is enabled but no frontmatter source is configured"
            )
        configured.extend(
            (document, index, True) for index, document in enumerate(sources.frontmatter)
        )
    configured.extend((document, index, False) for index, document in enumerate(profile.documents))

    # Rule-seed support applies to the complete manual. Report the first effective entry because no
    # source input may be returned when the requested seed is unsupported.
    first_document, first_index, first_is_frontmatter = configured[0]
    if rule_seed != _DEFAULT_RULE_SEED:
        entry_name = _entry_name(
            first_document, index=first_index, frontmatter=first_is_frontmatter
        )
        raise ValueError(
            f"{entry_name}: rule seed {rule_seed} is unsupported; "
            f"only default rule seed {_DEFAULT_RULE_SEED} can be resolved"
        )

    resolved: list[ResolvedDocument] = []
    for document, index, is_frontmatter in configured:
        entry_name = _entry_name(document, index=index, frontmatter=is_frontmatter)
        resolved.append(
            _resolve_profile_entry(
                document,
                sources=sources,
                cache_dir=cache_dir,
                root_dir=root_dir,
                language=language,
                entry_name=entry_name,
            )
        )

    return tuple(resolved)
