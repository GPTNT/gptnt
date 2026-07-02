"""Build the interactive (KTANE) submission: records -> experiments.parquet + submission.yaml."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING

from pydantic_ai import RunUsage
from rich.console import Console

from gptnt.cli.submission._identity import (
    build_capabilities_block,
    build_system_info,
    finalize_manifest,
    is_known_model_name,
    slugify,
)
from gptnt.cli.submission._io import find_player_records, load_suite, write_experiments
from gptnt.cli.submission._schema import (
    InteractiveSubmission,
    Provenance,
    SubmissionExperiment,
    SuiteIdentity,
    compute_interactive_stats,
)
from gptnt.experiments.db._extract import group_by_unique_experiment
from gptnt.experiments.models import ExperimentSummary
from gptnt.experiments.recorder.parquet import read_record_footer, read_run_usage

if TYPE_CHECKING:
    from pathlib import Path

    from gptnt.experiments.descriptor import ExperimentDescriptor
    from gptnt.experiments.recorder.parquet import RecordFooter
    from gptnt.experiments.suite import Suite

console = Console()


@dataclass(frozen=True, kw_only=True)
class _BuiltExperiment:
    """One experiment's submission row plus the descriptor and provenance it was built from."""

    row: SubmissionExperiment
    descriptor: ExperimentDescriptor
    gptnt_version: str
    git_sha: str | None


def _usage_totals(paths: list[Path]) -> dict[str, int]:
    """Sum the integer usage counters across an experiment's player files.

    The provider `details` breakdown is dropped: it does not sum cleanly and is not headline.
    """
    total = sum((read_run_usage(path) for path in paths), RunUsage())
    return {
        f"total_{key}": count for key, count in asdict(total).items() if isinstance(count, int)
    }


def _build_experiment(footers: list[RecordFooter], paths: list[Path]) -> _BuiltExperiment | None:
    """One experiment from a session's player files, or None if it never reached a bomb state.

    The final bomb state lives only in the defuser's footer, so it is the first non-null one.
    """
    final_bomb_state = next(
        (footer.final_bomb_state for footer in footers if footer.final_bomb_state is not None),
        None,
    )
    if final_bomb_state is None:
        return None

    canonical = footers[0]
    summary = ExperimentSummary.from_descriptor_and_bomb_state(
        descriptor=canonical.descriptor,
        final_bomb_state=final_bomb_state,
        is_hard_crash=any(footer.is_hard_crash for footer in footers),
        gptnt_version=canonical.gptnt_version,
        git_sha=canonical.git_sha,
    )
    return _BuiltExperiment(
        row=SubmissionExperiment.from_summary(
            summary=summary, final_bomb_state=final_bomb_state, usage=_usage_totals(paths)
        ),
        descriptor=canonical.descriptor,
        gptnt_version=canonical.gptnt_version,
        git_sha=canonical.git_sha,
    )


def _collect_by_suite(outputs_dir: Path) -> dict[str, list[_BuiltExperiment]]:
    """Read every completed experiment under an outputs dir, grouped by its recorded suite name."""
    records = find_player_records(outputs_dir)
    if not records:
        raise RuntimeError(
            f"No experiment records (experiment-*.parquet) found under {outputs_dir}"
        )

    by_suite: dict[str, list[_BuiltExperiment]] = defaultdict(list)
    skipped = 0
    for paths in group_by_unique_experiment(records).values():
        built = _build_experiment([read_record_footer(path) for path in paths], paths)
        if built is None:
            skipped += 1
            continue
        by_suite[built.descriptor.experiment_spec.suite_name].append(built)

    if skipped:
        console.print(f"[yellow]Skipped {skipped} experiment(s) that never reached a bomb state.")
    return by_suite


def _choose_suite(by_suite: dict[str, list[_BuiltExperiment]], suite_name: str | None) -> str:
    """Pick the suite: the named one, else the sole suite present, else fail listing them."""
    present = sorted(by_suite)
    if suite_name is not None:
        if suite_name not in by_suite:
            raise RuntimeError(f"No experiments for suite {suite_name!r}; found: {present}")
        return suite_name
    if len(present) == 1:
        return present[0]
    raise RuntimeError(f"Multiple suites in {present}; pass --suite to choose one.")


def _assemble_manifest(
    built: list[_BuiltExperiment], chosen: str, suite: Suite
) -> InteractiveSubmission:
    """Build the `submission.yaml` model from an experiment group and its frozen suite."""
    canonical = built[0]
    system = build_system_info(canonical.descriptor)
    if not is_known_model_name(system.model):
        console.print(
            f"[yellow]Model name {system.model!r} is not a known pydantic-ai id "
            "(expected for an open/HuggingFace checkpoint)."
        )

    capabilities = build_capabilities_block(canonical.descriptor)
    capfp = capabilities["defuser"]["fingerprint"][:8]
    run_date = min(experiment.descriptor.start_time for experiment in built).format_iso()[:10]
    return InteractiveSubmission(
        submission_id=f"{run_date}_{slugify(system.model)}_{chosen}@{suite.revision}_{capfp}",
        system=system,
        capabilities=capabilities,
        suite=SuiteIdentity(
            suite_name=chosen, suite_revision=suite.revision, suite_digest=suite.suite_digest
        ),
        provenance=Provenance(
            gptnt_version=canonical.gptnt_version, git_sha=canonical.git_sha, run_date=run_date
        ),
        stats=compute_interactive_stats([experiment.row for experiment in built]),
    )


def build_interactive_submission(outputs_dir: Path, suite_name: str | None, into: Path) -> Path:
    """Build one interactive submission bundle and return its directory."""
    by_suite = _collect_by_suite(outputs_dir)
    chosen = _choose_suite(by_suite, suite_name)
    built = by_suite[chosen]

    suite = load_suite(chosen)
    if any(experiment.row.suite_revision != suite.revision for experiment in built):
        console.print(
            f"[yellow]Records were run against a different revision of suite {chosen!r} than the "
            f"current config (rev {suite.revision}); stamping the current revision and digest."
        )

    manifest = _assemble_manifest(built, chosen, suite)
    capfp = manifest.capabilities["defuser"]["fingerprint"][:8]
    bundle_dir = into / slugify(manifest.system.model) / f"{chosen}@{suite.revision}_{capfp}"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    write_experiments(bundle_dir / "experiments.parquet", [experiment.row for experiment in built])
    finalize_manifest(bundle_dir, manifest)
    console.print(f"[bold green]Wrote submission bundle:[/bold green] {bundle_dir}")
    return bundle_dir
