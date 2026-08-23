from __future__ import annotations

import contextlib
import functools
import hashlib
import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self, cast

import orjson
from anyio.to_thread import run_sync
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PositiveInt,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)

from gptnt.ktane.manuals._compiler import build_artifact, input_identity, renderer_identity
from gptnt.ktane.manuals.compiler_sources import prepare_compiler_sources
from gptnt.ktane.manuals.download import download_manual_assets
from gptnt.ktane.manuals.resolution import ResolvedOfficialDocument
from gptnt.ktane.manuals.resolve import resolve_manual_profile

if TYPE_CHECKING:
    from collections.abc import Sequence

    from gptnt.ktane.manuals.profile import ManualProfile
    from gptnt.ktane.manuals.resolution import ResolvedDocument
    from gptnt.ktane.manuals.sources import ManualSources

_ARTIFACTS_DIRECTORY = "artifacts"
_DEFAULT_RULE_SEED = 1


class ManualArtifact(BaseModel):
    """A validated prepared manual with its ordered page content loaded."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    path: Path
    """Directory containing the compiled manual artifact."""

    artifact: str
    """Content-addressed key recorded in the artifact manifest."""

    inputs: list[dict[str, Any]]
    """Ordered compiler input identities recorded in the manifest."""

    renderer: dict[str, Any]
    """Renderer identity recorded in the manifest."""

    page_count: PositiveInt
    """Number of ordered text and PNG page pairs in the artifact."""

    files: list[dict[str, str]]
    """Relative artifact file paths and their SHA-256 digests."""

    pages: tuple[tuple[str, bytes], ...] = Field(
        default=(), exclude=True, repr=False, validate_default=True
    )
    """Ordered text and PNG page content loaded from the artifact."""

    @classmethod
    def load(
        cls,
        path: Path,
        *,
        expected_key: str | None = None,
        expected_inputs: list[dict[str, Any]] | None = None,
        expected_renderer: dict[str, Any] | None = None,
    ) -> Self:
        """Load a prepared manual directory and validate its complete contents."""
        return cls.model_validate(
            path,
            context={
                "expected_key": expected_key or path.name,
                "expected_inputs": expected_inputs,
                "expected_renderer": expected_renderer,
            },
        )

    @classmethod
    def key(cls, inputs: list[dict[str, Any]], renderer: dict[str, Any]) -> str:
        """Hash canonical input and renderer identity into an artifact key."""
        encoded = orjson.dumps(
            {"inputs": inputs, "renderer": renderer}, option=orjson.OPT_SORT_KEYS
        )
        return hashlib.sha256(encoded).hexdigest()

    @classmethod
    def describe_files(cls, path: Path) -> list[dict[str, str]]:
        """Describe every compiled manual file for its manifest."""
        paths = [path / "handbook.pdf"]
        paths.extend(sorted((path / "pages").glob("*")))
        files: list[dict[str, str]] = []
        for file_path in paths:
            with file_path.open("rb") as source:
                digest = hashlib.file_digest(source, "sha256").hexdigest()
            files.append({"path": file_path.relative_to(path).as_posix(), "sha256": digest})
        return files

    @model_validator(mode="before")
    @classmethod
    def _load_manifest(cls, raw_artifact: object) -> object:
        """Load the manifest when constructing an artifact from its directory."""
        if not isinstance(raw_artifact, Path):
            return raw_artifact
        try:
            manifest = orjson.loads((raw_artifact / "manifest.json").read_bytes())
        except (OSError, ValueError) as error:
            raise ValueError(f"manual artifact could not be read at {raw_artifact}") from error
        if isinstance(manifest, dict):
            return {**manifest, "path": raw_artifact}
        return {"path": raw_artifact}

    @field_validator("files")
    @classmethod
    def _validate_files(
        cls, files: list[dict[str, str]], validation: ValidationInfo
    ) -> list[dict[str, str]]:
        """Validate the manifest file entries and required page names."""
        page_count = cast("int | None", validation.data.get("page_count"))
        if page_count is None:
            return files
        expected = {"handbook.pdf"} | {
            f"pages/{page_number:04d}.{suffix}"
            for page_number in range(1, page_count + 1)
            for suffix in ("txt", "png")
        }
        if any(set(entry) != {"path", "sha256"} for entry in files):
            raise ValueError("manual artifact file entries require path and sha256")
        declared = [entry["path"] for entry in files]
        if len(declared) != len(expected) or set(declared) != expected:
            raise ValueError("manual artifact file list does not match its pages")
        return files

    @model_validator(mode="after")
    def _validate_file_paths(self) -> Self:
        """Keep every declared file inside the artifact directory."""
        for file_info in self.files:
            relative = Path(file_info["path"])
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("manual artifact file path leaves its directory")
        return self

    @model_validator(mode="after")
    def _validate_file_hashes(self) -> Self:
        """Validate the digest of every declared file."""
        for file_info in self.files:
            relative = Path(file_info["path"])
            try:
                with (self.path / relative).open("rb") as source:
                    digest = hashlib.file_digest(source, "sha256").hexdigest()
            except OSError as error:
                raise ValueError(f"manual artifact file could not be read: {relative}") from error
            if digest != file_info["sha256"]:
                raise ValueError(f"manual artifact file has changed: {relative}")
        return self

    @model_validator(mode="after")
    def _validate_directory(self) -> Self:
        """Reject files not declared by the manifest."""
        try:
            actual = {
                file_path.relative_to(self.path).as_posix()
                for file_path in self.path.rglob("*")
                if file_path.is_file() and file_path != self.path / "manifest.json"
            }
        except OSError as error:
            raise ValueError(f"manual artifact could not be read at {self.path}") from error
        if actual != {file_info["path"] for file_info in self.files}:
            raise ValueError("manual artifact contains unlisted files")
        return self

    @model_validator(mode="after")
    def _validate_identity(self, validation: ValidationInfo) -> Self:
        """Validate the key and optional compiler input identity."""
        context = cast("dict[str, Any]", validation.context or {})
        expected_key = cast("str", context.get("expected_key", self.path.name))
        expected_inputs = cast("list[dict[str, Any]] | None", context.get("expected_inputs"))
        expected_renderer = cast("dict[str, Any] | None", context.get("expected_renderer"))
        if self.artifact != expected_key or self.key(self.inputs, self.renderer) != expected_key:
            raise ValueError("manual artifact key does not match its inputs")
        if expected_inputs is not None and self.inputs != expected_inputs:
            raise ValueError("manual artifact inputs do not match")
        if expected_renderer is not None and self.renderer != expected_renderer:
            raise ValueError("manual artifact renderer does not match")
        return self

    @field_validator("pages")
    @classmethod
    def _load_pages(
        cls, pages: tuple[tuple[str, bytes], ...], validation: ValidationInfo
    ) -> tuple[tuple[str, bytes], ...]:
        """Load every ordered text and PNG page."""
        artifact_path = cast("Path | None", validation.data.get("path"))
        page_count = cast("int | None", validation.data.get("page_count"))
        if artifact_path is None or page_count is None:
            return pages
        pages_dir = artifact_path / "pages"
        try:
            return tuple(
                (
                    (pages_dir / f"{page_number:04d}.txt").read_text(encoding="utf-8"),
                    (pages_dir / f"{page_number:04d}.png").read_bytes(),
                )
                for page_number in range(1, page_count + 1)
            )
        except (OSError, UnicodeError) as error:
            raise ValueError(
                f"manual artifact pages could not be read at {artifact_path}"
            ) from error


def _remove_incomplete(path: Path) -> None:
    """Remove one invalid artifact path regardless of whether it is a file or directory."""
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()


def compile_manual(documents: Sequence[ResolvedDocument], *, cache_dir: Path) -> ManualArtifact:
    """Compile an ordered resolved-document sequence into a loaded manual artifact."""
    inputs = [input_identity(document) for document in documents]
    renderer = renderer_identity(documents)
    artifact_key = ManualArtifact.key(inputs, renderer)
    artifacts_dir = cache_dir / _ARTIFACTS_DIRECTORY
    artifact_dir = artifacts_dir / artifact_key
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(ValidationError):
        return ManualArtifact.load(
            artifact_dir,
            expected_key=artifact_key,
            expected_inputs=inputs,
            expected_renderer=renderer,
        )

    _remove_incomplete(artifact_dir)
    with tempfile.TemporaryDirectory(prefix=".manual-build-", dir=artifacts_dir) as temporary:
        build_dir = Path(temporary) / "artifact"
        build_dir.mkdir()
        page_count = build_artifact(documents, cache_dir=cache_dir, artifact_dir=build_dir)
        manifest = {
            "artifact": artifact_key,
            "inputs": inputs,
            "renderer": renderer,
            "page_count": page_count,
            "files": ManualArtifact.describe_files(build_dir),
        }
        _ = (build_dir / "manifest.json").write_bytes(
            orjson.dumps(manifest, option=orjson.OPT_APPEND_NEWLINE)
        )
        try:
            _ = ManualArtifact.load(
                build_dir,
                expected_key=artifact_key,
                expected_inputs=inputs,
                expected_renderer=renderer,
            )
        except ValidationError as error:
            raise RuntimeError("compiler produced an incomplete artifact") from error
        with contextlib.suppress(OSError):
            _ = build_dir.rename(artifact_dir)
        return ManualArtifact.load(
            artifact_dir,
            expected_key=artifact_key,
            expected_inputs=inputs,
            expected_renderer=renderer,
        )


def _profile_language(profile: ManualProfile, *, sources: ManualSources) -> str:
    """Choose the resolver language from frontmatter or the profile's first document."""
    if profile.include_frontmatter and sources.frontmatter:
        return sources.frontmatter[0].language
    return profile.documents[0].language


async def prepare_manual_artifacts(
    profiles: Sequence[ManualProfile], *, sources: ManualSources, cache_dir: Path, root_dir: Path
) -> dict[ManualProfile, ManualArtifact]:
    """Download, resolve, and compile each distinct default-rule profile once."""
    distinct_profiles = tuple(dict.fromkeys(profiles))
    if not distinct_profiles:
        return {}

    _ = await download_manual_assets(
        distinct_profiles, sources=sources, cache_dir=cache_dir, root_dir=root_dir
    )
    resolved_profiles = {
        profile: resolve_manual_profile(
            profile,
            sources=sources,
            cache_dir=cache_dir,
            root_dir=root_dir,
            language=_profile_language(profile, sources=sources),
            rule_seed=_DEFAULT_RULE_SEED,
        )
        for profile in distinct_profiles
    }

    if any(
        not isinstance(document, ResolvedOfficialDocument)
        for resolved in resolved_profiles.values()
        for document in resolved
    ):
        await prepare_compiler_sources(cache_dir)

    artifacts: dict[ManualProfile, ManualArtifact] = {}
    for profile, resolved in resolved_profiles.items():
        artifacts[profile] = await run_sync(  # noqa: WPS476
            functools.partial(compile_manual, resolved, cache_dir=cache_dir)
        )
    return artifacts
