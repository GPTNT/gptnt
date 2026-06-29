from pathlib import Path
from typing import Annotated

from cyclopts import Parameter
from rich.console import Console

from gptnt.common.paths import Paths, remove_empty_experiment_recorder_outputs
from gptnt.experiments.db._extract import compute_experiment_validity, group_by_unique_experiment

console = Console()
paths = Paths()


def cleanup_experiment_outputs(
    target: Annotated[
        Path,
        Parameter(
            help="Directory of experiment outputs to clean. Defaults to the recorder output dir."
        ),
    ] = paths.experiment_recorder_dir,
    *,
    execute: Annotated[
        bool,
        Parameter(
            name="--execute",
            help="Actually delete the files. Without it the command only previews.",
        ),
    ] = False,
) -> None:
    """Delete crashed or incomplete local experiment outputs, plus orphaned `.tmp` writes.

    Disk-only. Groups `experiment-*.parquet` files by experiment and drops any group that is not a
    valid, completed experiment (the validity the DB ingestion stamps). Also removes orphaned
    `experiment-*.parquet.tmp` files left by writes that crashed before the atomic rename. Previews
    by default; pass `--execute` to delete.
    """
    console.rule("[bold]Local Experiment Cleanup[/bold]")

    files = list(target.rglob("experiment-*.parquet"))
    tmp_files = list(target.rglob("experiment-*.parquet.tmp"))
    if not files and not tmp_files:
        console.print("[yellow]No experiment output files found. Nothing to do.[/yellow]")
        return

    grouped = group_by_unique_experiment(files)
    to_delete = [
        path
        for group_paths in grouped.values()
        if not compute_experiment_validity(group_paths)
        for path in group_paths
    ]

    for path in (*to_delete, *tmp_files):
        if execute:
            path.unlink(missing_ok=True)
        else:
            console.print(f"[dim][To Delete] {path}[/dim]")

    if execute:
        remove_empty_experiment_recorder_outputs(target)

    kept = len(files) - len(to_delete)
    verb = "Deleted" if execute else "Would delete"
    console.print(
        f"[green]{len(grouped)} experiment(s) scanned; keeping {kept} file(s), "
        f"{verb.lower()} {len(to_delete)} invalid + {len(tmp_files)} orphaned .tmp.[/green]"
    )
