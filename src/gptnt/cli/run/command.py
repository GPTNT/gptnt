from pathlib import Path
from typing import Annotated

from cyclopts import Parameter
from cyclopts.types import ExistingFile

from gptnt.cli.integrity import AllowModifiedBenchmarkOption
from gptnt.cli.run.manifest import RunManifest
from gptnt.cli.run.pipeline import run_pipeline


async def run(
    manifest: Annotated[ExistingFile, Parameter(help="Path to the run.yaml manifest.")],
    *,
    force: Annotated[
        bool,
        Parameter(
            name="--force",
            help=(
                "Run despite ordinary doctor failures; does not bypass protected-content, roster, "
                "or manual-preparation failures."
            ),
        ),
    ] = False,
    allow_modified_benchmark: AllowModifiedBenchmarkOption = False,
    interactive: Annotated[
        bool,
        Parameter(
            name=("--interactive", "-i"),
            help="Stream process logs to the terminal (like docker compose).",
        ),
    ] = False,
) -> None:
    """Run a benchmark: doctor, prepare required manuals, spawn, submit, and monitor.

    Specs are NOT generated here. Run them with `gptnt generate <manifest>` first; this command
    loads the pre-generated specs from `output/experiment_specs/<manifest-stem>/`. Manual
    preparation occurs after resume filtering and before any process starts.
    """
    loaded = RunManifest.from_path(manifest)
    await run_pipeline(
        loaded,
        manifest_stem=Path(manifest).stem,
        force=force,
        interactive=interactive,
        allow_modified_benchmark=allow_modified_benchmark,
    )
