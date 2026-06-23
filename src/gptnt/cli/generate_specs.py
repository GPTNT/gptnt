from pathlib import Path
from typing import Annotated

from cyclopts import Parameter
from cyclopts.types import ExistingFile
from rich.console import Console

from gptnt.cli.doctor.command import diagnose
from gptnt.cli.run.manifest import RunManifest
from gptnt.common.paths import Paths
from gptnt.experiments.specs_store import write_specs_to_dir

console = Console()


async def generate(
    manifest: Annotated[ExistingFile, Parameter(help="Path to the run.yaml manifest.")],
    output_dir: Annotated[
        Path | None, Parameter(help="Directory to write specs to.", env_var="EXPERIMENT_SPECS_DIR")
    ] = None,
) -> None:
    """Generate experiment specs from a run.yaml into output/experiment_specs/<manifest-stem>/.

    Override the output directory with the `EXPERIMENT_SPECS_DIR` env var or the `--output-dir`
    flag.
    """
    loaded = RunManifest.from_path(manifest)

    # Offline gate: validate the roster + compose the specs, but skip run-time infra checks.
    diagnosis = await diagnose(loaded, include_infra=False)
    if diagnosis.failed:
        console.print(
            "\n[bold red]Doctor found problems.[/bold red] Fix the ✗ rows above before generating."
        )
        raise RuntimeError("doctor found problems; fix the rows above before generating")

    if diagnosis.run_plan is None or not diagnosis.run_plan.specs:
        console.print(
            "[bold red]No experiment specs were generated from this manifest.[/bold red]"
        )
        raise RuntimeError("no experiment specs were generated from this manifest")

    out_dir = output_dir or Paths().experiment_specs.joinpath(Path(manifest).stem)
    written = write_specs_to_dir(diagnosis.run_plan.specs, out_dir)

    console.print(f"\n[bold green]Wrote {len(written)} spec(s) to[/bold green] {out_dir}")
