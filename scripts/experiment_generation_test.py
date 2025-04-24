import asyncio
import json
import shutil
import sys
from itertools import combinations
from pathlib import Path

import httpx
import numpy as np
import structlog
from deepdiff import DeepDiff
from omegaconf import OmegaConf

from gptnt.common.logger import configure_logging
from gptnt.common.paths import Paths
from gptnt.ktane.client import KtaneClient
from gptnt.ktane.experiments.experiments import ExperimentSpec
from gptnt.ktane.mission_spec import KtaneMissionSpec
from gptnt.ktane.state.bomb import BombState
from gptnt.ktane.state.modules import KtaneComponent

configure_logging()

logger = structlog.get_logger()

DIFFERENCE_THRESHOLD: float = 0.5

paths = Paths()

SEED_MIN: int = 1
SEED_MAX: int = 51

unique_experiments: Path = paths.storage.joinpath("unique_experiments")
bomb_states: Path = paths.storage.joinpath("bomb_states")
single_modules: Path = bomb_states.joinpath("single_module")
repeated_modules_2: Path = bomb_states.joinpath("repeated_modules_2")
repeated_modules_5: Path = bomb_states.joinpath("repeated_modules_5")
multiple_modules_2: Path = bomb_states.joinpath("multiple_modules_2")
multiple_modules_2_front: Path = bomb_states.joinpath("multiple_modules_2_front")
multiple_modules_5: Path = bomb_states.joinpath("multiple_modules_5")
multiple_modules_n: Path = bomb_states.joinpath("multiple_modules_n")

wires: Path = single_modules.joinpath("Wires")
big_button: Path = single_modules.joinpath("Big_button")
keypad: Path = single_modules.joinpath("Keypad")
simon: Path = single_modules.joinpath("Simon")
whose_on_first: Path = single_modules.joinpath("Whos_On_First")
memory: Path = single_modules.joinpath("Memory")
morse_code: Path = single_modules.joinpath("Morse_code")
venn: Path = single_modules.joinpath("Venn")
wire_sequence: Path = single_modules.joinpath("Wire_Sequence")
maze: Path = single_modules.joinpath("Maze")
password: Path = single_modules.joinpath("Password")
needy_vent_gas: Path = single_modules.joinpath("Needy_Vent_Gas")
needy_capacitor: Path = single_modules.joinpath("Needy_Capacitor")
needy_knob: Path = single_modules.joinpath("Needy_Knob")

src: Path = paths.root.joinpath("src")
gptnt: Path = src.joinpath("gptnt")
entrypoints: Path = gptnt.joinpath("entrypoints")

seed_differences_path: Path = paths.storage.joinpath("seed_differences")


async def main() -> None:
    """Run to get the seed with best difference rating."""
    seed_differences: list[tuple[int, list[float]]] = []
    seed_range = range(SEED_MIN, SEED_MAX)
    for seed in seed_range:
        for directory in [bomb_states, paths.experiments, unique_experiments]:
            if directory.exists():
                shutil.rmtree(directory)
        check_paths_exist()

        logger.info(f"Processing seed: {seed}")

        # Step 1: Update the seed in the configuration file
        config_path = paths.configs / "experiment_generator.yaml"
        config = OmegaConf.load(config_path)
        config.mission_generator.seed = seed
        OmegaConf.save(config, config_path)

        # Step 2: Run the experiment generation script
        python_executable = sys.executable
        process = await asyncio.create_subprocess_exec(
            python_executable,
            str(entrypoints / "generate_experiments.py"),
            "-m",
            "experiment=e1,e2,e3,e4_1,e4_2,e5_1,e5_2,e5_3,e6_1,e6_2,e6_3",
        )
        stdout, stderr = await process.communicate()

        logger.info(f"Experiment generation completed for seed {seed}")

        # Step 3: Run the difference rating tests
        difference_rating = await get_seed_difference_rating()
        if difference_rating is None:
            continue
        seed_differences.append((seed, difference_rating))
        # write the seed and difference rating to a file
        with Path.open(seed_differences_path / f"seed_{seed}_differences.json", "w") as seed_file:
            json.dump(difference_rating, seed_file)

    seed_directory = seed_differences_path
    top_seeds = rank_seeds(seed_directory)[:3]  # Get the top 3 seeds
    logger.info("Top 3 seeds based on average difference ratings:")
    for rank, (seed, average) in enumerate(top_seeds, start=1):
        logger.info(f"Rank {rank}: Seed {seed}, Average Difference: {average:.2f}")


def flatten_json(data: list[float | list[float]] | list[float] | float) -> list[float]:
    """Flattens a nested JSON object or list and extracts all numerical values."""
    flat_list = []
    if isinstance(data, list):
        for data_value in data:
            flat_list.extend(flatten_json(data_value))
    else:  # Only keep numerical values
        flat_list.append(data)
    return flat_list


def calculate_average_for_seed(json_file: Path) -> float:
    """Calculates the average of all numerical values in a flattened .json file."""
    with Path.open(json_file) as json_file_obj:
        data = json.load(json_file_obj)
    flattened_values = flatten_json(data)
    return float(np.mean(flattened_values)) if flattened_values else float(0)


def rank_seeds(seed_directory: Path) -> list[tuple[int, float]]:
    """Ranks seeds based on the average of their flattened numerical values."""
    seed_scores = []
    for json_file in seed_directory.glob("*.json"):
        seed = int(json_file.stem.split("_")[1])  # Extract seed from filename
        average = calculate_average_for_seed(json_file)
        seed_scores.append((seed, average))
    return sorted(seed_scores, key=lambda lambda_key: lambda_key[1], reverse=True)


async def get_seed_difference_rating() -> list[float] | None:
    """Checks if the bombs used in the experiment are different enough."""
    unique_missions: set[tuple[KtaneMissionSpec, str]] = get_unique_missions()

    mission_specs: dict[
        str, dict[KtaneComponent, list[KtaneMissionSpec]] | list[KtaneMissionSpec]
    ] = {
        "single_module": {component: [] for component in KtaneComponent},
        "repeated_modules_2": [],
        "repeated_modules_5": [],
        "multiple_modules_2": [],
        "multiple_modules_2_front": [],
        "multiple_modules_n": [],
        "multiple_modules_5": [],
    }

    client = KtaneClient(client=httpx.AsyncClient(base_url="http://localhost:8085"))

    # Put missions into correct lists
    for mission_spec, condition in unique_missions:
        mission_spec.time_scale = 5.0
        if condition == "single_module":
            component: KtaneComponent = mission_spec.components[0]  # Extract the component
            _ = mission_specs["single_module"][component].append(mission_spec)  # pyright: ignore[reportCallIssue, reportArgumentType]

        else:
            _ = mission_specs[condition].append(mission_spec)  # pyright: ignore[reportAttributeAccessIssue]

    _ = await save_state(
        multiple_modules_2,
        client,
        mission_specs["multiple_modules_2"],  # pyright: ignore[reportArgumentType]
    )
    if check_modules_on_both_sides(multiple_modules_2) is None:
        return None

    _ = await save_state(
        multiple_modules_n,
        client,
        mission_specs["multiple_modules_n"],  # pyright: ignore[reportArgumentType]
    )
    if check_modules_on_both_sides(multiple_modules_n) is None:
        return None

    _ = await save_single_module_state(client, mission_specs["single_module"])  # pyright: ignore[reportArgumentType]

    _ = await save_state(
        repeated_modules_2,
        client,
        mission_specs["repeated_modules_2"],  # pyright: ignore[reportArgumentType]
    )

    _ = await save_state(
        repeated_modules_5,
        client,
        mission_specs["repeated_modules_5"],  # pyright: ignore[reportArgumentType]
    )

    _ = await save_state(
        multiple_modules_2_front,
        client,
        mission_specs["multiple_modules_2_front"],  # pyright: ignore[reportArgumentType]
    )

    seed_difference_rating = []

    logger.info("removing unneeded info from .json files")
    process_directory()

    logger.info("checking if single module bombs are different enough")
    seed_difference_rating.append(single_module_difference())
    logger.info("checking if repeated modules 2 bombs are different enough")
    seed_difference_rating.append(
        (intra_bomb_difference(repeated_modules_2), inter_bomb_difference(repeated_modules_2))
    )
    logger.info("checking if repeated modules 5 bombs are different enough")
    seed_difference_rating.append(
        (intra_bomb_difference(repeated_modules_5), inter_bomb_difference(repeated_modules_5))
    )
    logger.info("checking if multiple modules 2 front bombs are different enough")
    seed_difference_rating.append(intra_bomb_difference(multiple_modules_2_front))
    logger.info("checking if multiple modules 2 bombs are different enough")
    seed_difference_rating.append(intra_bomb_difference(multiple_modules_2))
    logger.info("checking if multiple modules n bombs are different enough")
    seed_difference_rating.append(
        (intra_bomb_difference(multiple_modules_n), inter_bomb_difference(multiple_modules_n))
    )

    return seed_difference_rating


def get_unique_missions() -> set[tuple[KtaneMissionSpec, str]]:
    """Iterates through all experiments and returns unique missions."""
    all_missions = []

    for json_file in paths.experiments.glob("*.json"):
        specs = ExperimentSpec.model_validate_json(json_file.read_text())
        all_missions.append((specs.mission_spec, specs.condition))
    unique_missions = set(all_missions)

    return unique_missions


def check_modules_on_both_sides(path: Path) -> int | None:
    """Check if the bomb has modules on both sides."""
    all_bombs = list(path.glob("*.json"))
    for bomb in all_bombs:
        modules = json.loads(bomb.read_text()).get("modules", [])
        has_front = any(module.get("onFront") for module in modules)
        has_back = any(not module.get("onFront") for module in modules)
        if has_front and has_back:
            logger.info("Bomb has modules on both sides")
            return 1
        logger.warning("Bomb has modules only on one side")
        return None
    return None


async def save_single_module_state(
    client: KtaneClient, mission_specs: dict[KtaneComponent, list[KtaneMissionSpec]]
) -> None:
    """Saving single module bomb states."""
    for component_missions in mission_specs.values():
        for bomb in component_missions:
            bomb_state: BombState = await get_bomb_details(client, bomb)
            save(single_modules / bomb.components[0].name, bomb.seed, bomb.components, bomb_state)


async def save_state(
    path: Path, client: KtaneClient, mission_specs: list[KtaneMissionSpec]
) -> None:
    """Saving the state of a bomb."""
    for bombs in mission_specs:
        bomb_state: BombState = await get_bomb_details(client, bombs)
        save(path, bombs.seed, bombs.components, bomb_state)


def check_paths_exist() -> None:
    """Makes sure all the folders needed exist."""
    paths.experiments.mkdir(parents=True, exist_ok=True)
    unique_experiments.mkdir(parents=True, exist_ok=True)
    bomb_states.mkdir(parents=True, exist_ok=True)
    single_modules.mkdir(parents=True, exist_ok=True)
    wires.mkdir(parents=True, exist_ok=True)
    big_button.mkdir(parents=True, exist_ok=True)
    keypad.mkdir(parents=True, exist_ok=True)
    simon.mkdir(parents=True, exist_ok=True)
    whose_on_first.mkdir(parents=True, exist_ok=True)
    memory.mkdir(parents=True, exist_ok=True)
    morse_code.mkdir(parents=True, exist_ok=True)
    venn.mkdir(parents=True, exist_ok=True)
    wire_sequence.mkdir(parents=True, exist_ok=True)
    maze.mkdir(parents=True, exist_ok=True)
    password.mkdir(parents=True, exist_ok=True)

    repeated_modules_2.mkdir(parents=True, exist_ok=True)
    repeated_modules_5.mkdir(parents=True, exist_ok=True)
    multiple_modules_2.mkdir(parents=True, exist_ok=True)
    multiple_modules_2_front.mkdir(parents=True, exist_ok=True)
    multiple_modules_n.mkdir(parents=True, exist_ok=True)

    seed_differences_path.mkdir(parents=True, exist_ok=True)


def save(path: Path, seed: int, modules: list[KtaneComponent], bomb_state: BombState) -> None:
    """Saves the bomb state to a file."""
    file_name = str(seed) + "".join(f"_{component.name}" for component in modules)
    file_save = path.joinpath(file_name).with_suffix(".json").write_text(json.dumps(bomb_state))
    assert file_save > 0


def process_directory() -> None:
    """Recursively process all .json files in a directory and its subdirectories."""
    directory = bomb_states
    for json_file in directory.rglob("*.json"):  # Recursively find all .json files
        dump_unneeded_info(json_file)


def remove_keys_recursively(data, keys_to_remove: list[str]) -> None:  # noqa: ANN001
    """Recursively remove specified keys from dictionaries and lists."""
    if isinstance(data, dict):
        # Remove keys from the current dictionary
        for key in keys_to_remove:
            if key in data:
                del data[key]
        # Recursively process the remaining values
        for value_to_be_removed in data.values():
            remove_keys_recursively(value_to_be_removed, keys_to_remove)
    elif isinstance(data, list):
        # Recursively process each item in the list
        for item_to_be_removed in data:
            remove_keys_recursively(item_to_be_removed, keys_to_remove)


def dump_unneeded_info(file_path: Path) -> None:
    """Perform an operation on a JSON file."""
    # Read the JSON file
    with Path.open(file_path) as file_to_be_cleaned:
        data = json.load(file_to_be_cleaned)

    # Keys to remove
    keys_to_remove = [
        "isHeld",
        "isSolved",
        "inFocus",
        "stage",
        "numRows",
        "numColumns",
        "currentFrequency",
        "solveProgress",
        "panel",
        "stripColor",
        "name",
        "isCut",
    ]

    # Apply the recursive removal to the "modules" section
    if "modules" in data:
        for module in data["modules"]:
            remove_keys_recursively(module, keys_to_remove)

            # Check if the module is a Keypad module
            if all(key in module for key in ["topLeft", "topRight", "bottomLeft", "bottomRight"]):
                # Remove the `color` attribute from each position
                for position in ["topLeft", "topRight", "bottomLeft", "bottomRight"]:
                    if position in module and "color" in position:
                        del module[position]["color"]

    # Write the updated JSON back to the file
    with Path.open(file_path, "w") as file_to_write_to:
        json.dump(data, file_to_write_to, indent=4)


def count_unique_attributes(data1, data2) -> int:  # noqa: PLR0911, ANN001
    """Counts all attributes from two inputs, counting shared attributes only once."""
    if isinstance(data1, dict) and isinstance(data2, dict):
        # Combine keys from both dictionaries
        unique_keys = set(data1.keys()).union(data2.keys())
        # Recursively count attributes in the values
        return sum(
            count_unique_attributes(data1.get(key, None), data2.get(key, None))
            for key in unique_keys
        )
    if isinstance(data1, list) and isinstance(data2, list):
        # Combine unique items from both lists
        unique_items = set(map(json.dumps, data1)).union(set(map(json.dumps, data2)))
        # Recursively count attributes in each unique item
        return sum(
            count_unique_attributes(json.loads(item_to_be_counted), {})
            for item_to_be_counted in unique_items
        )
    if isinstance(data1, dict):
        # Count all attributes in the dictionary
        return sum(
            count_unique_attributes(value_to_be_counted, {})
            for value_to_be_counted in data1.values()
        ) + len(data1)
    if isinstance(data2, dict):
        # Count all attributes in the dictionary
        return sum(
            count_unique_attributes({}, value_to_be_counted)
            for value_to_be_counted in data2.values()
        ) + len(data2)
    if isinstance(data1, list):
        # Count all attributes in the list
        return sum(count_unique_attributes(item_to_be_counted, {}) for item_to_be_counted in data1)
    if isinstance(data2, list):
        # Count all attributes in the list
        return sum(count_unique_attributes({}, item_to_be_counted) for item_to_be_counted in data2)
    # Count primitive values as 1 if they exist
    return 1


def single_module_difference() -> float:
    """Checks if the bombs used in the experiment are different enough."""
    avg_difference = []
    for folder in single_modules.iterdir():
        # Get all JSON files in the folder
        bomb_files = list(folder.glob("*.json"))

        # Perform combinations for the modules in the folder
        for bomb1, bomb2 in combinations(bomb_files, 2):
            b1 = json.loads(bomb1.read_text())["modules"]
            b2 = json.loads(bomb2.read_text())["modules"]

            # Use DeepDiff to calculate the differences
            diff = DeepDiff(b1, b2)

            total_differences = sum(len(diff_value) for diff_value in diff.values())

            number_of_attributes = count_unique_attributes(b1, b2)

            # Normalize the number of differences by the total number of attributes
            diff_ratio = total_differences / number_of_attributes

            avg_difference.append(diff_ratio)
    return float(np.mean(avg_difference))


def intra_bomb_difference(path: Path) -> float:
    """Within a list of bombs, check how similar the modules are."""
    all_bombs = list(path.glob("*.json"))
    avg_diff = []
    for bomb in all_bombs:
        modules = json.loads(bomb.read_text()).get("modules", [])
        for module1, module2 in combinations(modules, 2):
            # Use DeepDiff to calculate the differences
            diff = DeepDiff(module1, module2)

            total_differences = sum(len(diff_value) for diff_value in diff.values())

            number_of_attributes = count_unique_attributes(module1, module2)

            # Normalize the number of differences by the total number of attributes
            diff_ratio = total_differences / number_of_attributes
            avg_diff.append(diff_ratio)

    return float(np.mean(avg_diff))


def inter_bomb_difference(path: Path) -> float:
    """Between a list of bombs, check how similar the modules are."""
    all_bombs = list(path.glob("*.json"))
    avg_diff = []
    # check if the bombs themselves are different enough
    for bomb1, bomb2 in combinations(all_bombs, 2):
        b1 = json.loads(bomb1.read_text())["modules"]
        b2 = json.loads(bomb2.read_text())["modules"]

        diff = DeepDiff(b1, b2)

        total_differences = sum(len(diff_value) for diff_value in diff.values())

        number_of_attributes = count_unique_attributes(b1, b2)

        diff_ratio = total_differences / number_of_attributes
        avg_diff.append(diff_ratio)

    return float(np.mean(avg_diff))


async def get_bomb_details(client: KtaneClient, mission_spec: KtaneMissionSpec) -> BombState:
    """Starts a game and collects the BombState for each mission."""
    time_until_retry = 5
    while not await client.healthcheck():
        logger.warning("Waiting for server to start")
        await asyncio.sleep(1)

    mission_state = await client.start_mission(mission_spec)
    tried_to_start = 0
    while not mission_state:
        logger.warning("Waiting for mission to start")
        await asyncio.sleep(1)
        tried_to_start += 1
        if tried_to_start > time_until_retry:
            mission_state = await client.start_mission(mission_spec)
            tried_to_start = 0

    await asyncio.sleep(5)

    # Retrieve the bomb state
    bomb_state = await client.get_state()

    assert bomb_state is not None

    # Reset the game after processing
    reset = await client.reset()

    assert reset

    await asyncio.sleep(5)

    return bomb_state


if __name__ == "__main__":
    asyncio.run(main())
