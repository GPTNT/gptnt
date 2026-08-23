"""Factories for small prepared manual artifacts."""

from pathlib import Path

import pymupdf

from gptnt.ktane.manuals.artifacts import ManualArtifact, compile_manual
from gptnt.ktane.manuals.resolution import OfficialManualProvenance, ResolvedOfficialDocument
from gptnt.ktane.manuals.sources import OfficialPageRange


def make_compiled_manual(
    root: Path, *, name: str = "fixture", text: str = "PREPARED MANUAL"
) -> ManualArtifact:
    """Compile one single-page official-PDF fixture without invoking Chromium."""
    source = root / f"{name}.pdf"
    with pymupdf.open() as document:
        page = document.new_page(width=612, height=792)
        _ = page.insert_text((72, 72), text, fontsize=18)
        document.save(source)
    resolved = ResolvedOfficialDocument(
        document_id=name,
        language="en",
        source="official",
        source_path=source,
        page_range=OfficialPageRange(first=1, last=1),
        provenance=OfficialManualProvenance(
            version="fixture", url=f"https://manual.test/{name}.pdf"
        ),
        supports_requested_rule_seed=True,
    )
    return compile_manual([resolved], cache_dir=root / "cache")
