from pathlib import Path
from typing import Annotated

from cyclopts import Parameter
from cyclopts.types import ExistingFile

from gptnt.cli.integrity import ForceOption
from gptnt.cli.run._pipeline import run_pipeline
from gptnt.cli.run.manifest import RunManifest


async def run(
    manifest: Annotated[ExistingFile, Parameter(help="Path to the run.yaml manifest.")],
    *,
    force: ForceOption = False,
    interactive: Annotated[
        bool,
        Parameter(
            name=("--interactive", "-i"),
            help="Stream process logs to the terminal (like docker compose).",
        ),
    ] = False,
) -> None:
    """Run a benchmark: doctor, spawn, submit, and monitor.

    Specs are NOT generated here. Run them with `gptnt generate <manifest>` first; this command
    loads the pre-generated specs from `output/experiment_specs/<manifest-stem>/`. Doctor requires
    the selected suites' manuals to be compiled before any process starts.
    """
    loaded = RunManifest.from_path(manifest)
    await run_pipeline(
        loaded, manifest_stem=Path(manifest).stem, force=force, interactive=interactive
    )
