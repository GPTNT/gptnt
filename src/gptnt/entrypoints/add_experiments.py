from gptnt.api.experiment_manager_client import ExperimentManagerClient
from gptnt.common.paths import Paths
from gptnt.entrypoints._async_typer import AsyncTyper
from gptnt.ktane.experiments.experiments import ExperimentSpec

app = AsyncTyper()
paths = Paths()


@app.command()
async def add_experiments(host: str = "localhost", port: int = 8099) -> None:
    """Load all experiment JSON files from the experiments directory."""
    experiment_paths = paths.experiments.rglob("*.json")

    all_experiments = [
        ExperimentSpec.model_validate_json(path.read_text()) for path in experiment_paths
    ]

    client = ExperimentManagerClient(f"http://{host}:{port}")

    for experiment in all_experiments:
        _ = await client.add_experiment(experiment)  # noqa: WPS476


if __name__ == "__main__":
    app()
