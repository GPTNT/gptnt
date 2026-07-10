from typing import TYPE_CHECKING, Annotated

import hydra
from cyclopts import Parameter
from rich.console import Console

from gptnt.common.hydra import load_config
from gptnt.common.paths import Paths

if TYPE_CHECKING:
    from gptnt.experiments.generation.missions import MissionGenerator

console = Console()


def generate_missions(
    name: Annotated[
        str, Parameter(help="Name of the mission set under configs/missions/ to materialise.")
    ],
) -> None:
    """Materialise a mission set from its recipe into configs/missions/<name>/.

    The recipe at configs/missions/recipes/<name>.yaml drives a `MissionGenerator`. This is the
    authoring side of the mission library. The run path only loads the generated files. It never
    generates.
    """
    cfg = load_config(config_name=f"missions/recipes/{name}")
    generator: MissionGenerator = hydra.utils.instantiate(cfg.generator)

    out_dir = Paths().missions_library / name
    out_dir.mkdir(parents=True, exist_ok=True)

    missions = list(generator.generate())
    for mission in missions:
        modules = "-".join(sorted(component.value for component in mission.components))
        _ = out_dir.joinpath(f"{modules}-{mission.seed}.json").write_text(
            mission.model_dump_json()
        )

    console.print(f"[bold green]Wrote {len(missions)} mission(s) to[/bold green] {out_dir}")
