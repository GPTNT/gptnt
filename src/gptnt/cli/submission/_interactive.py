from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

import hydra
import pyarrow as pa
from pyarrow import parquet as pq

from gptnt.cli.submission._bundle import (
    BundleName,
    create_submission_player_entry,
    write_bundle_to_dir,
)
from gptnt.cli.submission._schema import (
    InteractiveSubmission,
    SubmissionExperiment,
    Submitter,
    SuiteIdentity,
)
from gptnt.common.hydra import load_config
from gptnt.experiments.db.read import load_experiment_summaries, load_final_states_and_usage
from gptnt.experiments.db.schema import EXPORT_CONTEXT_MARKER
from gptnt.experiments.generation.pipeline import CONFIG_NAME
from gptnt.experiments.provenance import ProvenanceMixin

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

    from gptnt.experiments.suite import Suite
    from gptnt.players.specification import PlayerCapabilities


def load_suite(suite_name: str) -> Suite:
    """Compose and instantiate one suite exactly as generation and `test_frozen_suites` do."""
    return hydra.utils.instantiate(
        load_config(config_name=CONFIG_NAME, overrides=[f"suites={suite_name}"]).suite
    )


def _get_distinct_experts(rows: list[SubmissionExperiment]) -> list[PlayerCapabilities]:
    """Every distinct expert (by capability fingerprint) paired with the defuser, name-sorted."""
    experts: dict[str, PlayerCapabilities] = {}
    for row in rows:
        if row.expert_capabilities is not None:
            experts[row.expert_capabilities.fingerprint] = row.expert_capabilities
    return sorted(experts.values(), key=lambda caps: caps.player_name)


def _write_experiments_to_file(
    experiments: list[SubmissionExperiment], *, file_path: Path
) -> None:
    """Write the rows to `experiments.parquet` using the model's `db`-context serialization."""
    rows = [
        experiment.model_dump(context={"mode": EXPORT_CONTEXT_MARKER})
        for experiment in experiments
    ]
    _ = pq.write_table(pa.Table.from_pylist(rows), file_path)


def read_experiments_from_file(file_path: Path) -> list[SubmissionExperiment]:
    """Read `experiments.parquet` back into typed rows (the JSON columns parse back on input)."""
    table = pq.read_table(file_path)
    return [SubmissionExperiment.model_validate(row) for row in table.to_pylist()]


def gather_experiments_for_suite(
    db_path: Path, suite: Suite, model_names: Iterable[str] | None = None
) -> list[SubmissionExperiment]:
    """Collate all the experiments for a given suite, filtered by model names if provided."""
    summaries = load_experiment_summaries(
        db_path, suite_name=suite.name, suite_revision=suite.revision, model_names=model_names
    )
    if not summaries:
        return []

    final_states = load_final_states_and_usage(
        db_path, [summary.session_id for summary in summaries]
    )
    all_experiments = []
    for summary in summaries:
        # If there is an issue with the session ID, this should fail.
        final_bomb_state, usage_by_role = final_states[summary.session_id]
        all_experiments.append(
            SubmissionExperiment.from_summary(
                summary=summary, final_bomb_state=final_bomb_state, usage_by_role=usage_by_role
            )
        )
    return all_experiments


def group_experiments_by_model(
    experiments: list[SubmissionExperiment],
) -> list[tuple[str, list[SubmissionExperiment]]]:
    """Group experiments into one `(model_name, rows)` bundle group per model, name-sorted.

    Grouped by defuser capability fingerprint (not name), so the same model run with different
    capabilities lands in different bundles.
    """
    groups: dict[str, list[SubmissionExperiment]] = defaultdict(list)
    for row in experiments:
        groups[row.defuser_capability_fingerprint].append(row)

    return sorted(
        ((rows[0].defuser_capabilities.player_name, rows) for rows in groups.values()),
        key=lambda group: group[0],
    )


def write_interactive_bundle(
    experiments: list[SubmissionExperiment], suite: Suite, output_dir: Path
) -> None:
    """Write one per-model bundle (experiments.parquet + manifest)."""
    canonical = experiments[0]
    defuser_capabilities = canonical.defuser_capabilities

    name = BundleName(
        player_name=defuser_capabilities.player_name,
        target=f"{suite.name}@{suite.revision}",
        fingerprint=defuser_capabilities.fingerprint,
        run_date=min(row.experiment_descriptor.start_time for row in experiments),
    )

    manifest = InteractiveSubmission(
        submission_id=name.submission_id,
        submitter=Submitter(),
        players=[
            create_submission_player_entry("defuser", canonical.defuser_capabilities),
            *(
                create_submission_player_entry("expert", caps)
                for caps in _get_distinct_experts(experiments)
            ),
        ],
        suite=SuiteIdentity.from_suite(suite),
        provenance=ProvenanceMixin(
            gptnt_version=canonical.gptnt_version, git_sha=canonical.git_sha
        ),
        run_date=name.run_date,
    )

    write_bundle_to_dir(
        output_path=output_dir,
        bundle_name=name,
        submission_manifest=manifest,
        write_payload_fn=lambda bundle_dir: _write_experiments_to_file(
            experiments, file_path=bundle_dir / "experiments.parquet"
        ),
    )
