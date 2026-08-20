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
                "Run despite ordinary doctor failures. This cannot bypass protected-content or "
                "run-roster failures."
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
    """Run a benchmark end-to-end from a run.yaml: doctor → spawn → submit → monitor.

    Specs are NOT generated here — run them with `gptnt generate <manifest>` first; this command
    loads the pre-generated specs from `output/experiment_specs/<manifest-stem>/`.
    """
    loaded = RunManifest.from_path(manifest)
    await run_pipeline(
        loaded,
        manifest_stem=Path(manifest).stem,
        force=force,
        interactive=interactive,
        allow_modified_benchmark=allow_modified_benchmark,
    )
