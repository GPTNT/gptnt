import asyncio
import atexit
import json
import os
import shutil
import sys
from contextlib import suppress
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Any

import anyio
import numpy as np
import structlog
from deepdiff import DeepDiff
from tqdm.asyncio import tqdm

from gptnt.common.async_ops import until
from gptnt.common.logger import configure_logging
from gptnt.common.paths import Paths
from gptnt.common.servers import get_available_port
from gptnt.ktane.client import KtaneClient
from gptnt.ktane.executable import get_executable_path
from gptnt.ktane.experiments.experiments import ExperimentSpec
from gptnt.ktane.mission_spec import KtaneMissionSpec
from gptnt.ktane.state.game import GameState
from gptnt.ktane.state.modules import KtaneComponent

configure_logging()

logger = structlog.get_logger()
paths = Paths()

DIFFERENCE_THRESHOLD: float = 0.5

SEED_MIN: int = 1
SEED_MAX: int = 51

unique_experiments: Path = paths.storage.joinpath("unique_experiments")
unique_experiments.mkdir(parents=True, exist_ok=True)
all_bomb_states: Path = paths.storage.joinpath("bomb_states")
all_bomb_states.mkdir(parents=True, exist_ok=True)
seed_differences_path: Path = paths.storage.joinpath("seed_differences")
seed_differences_path.mkdir(parents=True, exist_ok=True)

entrypoints: Path = paths.root.joinpath("src", "gptnt", "entrypoints")


@dataclass
class SeedPaths:
    seed: int
    all_bomb_states: Path

    def __post_init__(self) -> None:
        self.bomb_states: Path = self.all_bomb_states.joinpath(f"seed_{self.seed}")

        self.single_modules: Path = self.bomb_states.joinpath("single_module")
        self.repeated_modules_2: Path = self.bomb_states.joinpath("repeated_modules_2")
        self.repeated_modules_5: Path = self.bomb_states.joinpath("repeated_modules_5")
        self.multiple_modules_2: Path = self.bomb_states.joinpath("multiple_modules_2")
        self.multiple_modules_2_front: Path = self.bomb_states.joinpath("multiple_modules_2_front")
        self.multiple_modules_5: Path = self.bomb_states.joinpath("multiple_modules_5")
        self.multiple_modules_n: Path = self.bomb_states.joinpath("multiple_modules_n")

        self.wires: Path = self.single_modules.joinpath("Wires")
        self.big_button: Path = self.single_modules.joinpath("Big_button")
        self.keypad: Path = self.single_modules.joinpath("Keypad")
        self.simon: Path = self.single_modules.joinpath("Simon")
        self.whose_on_first: Path = self.single_modules.joinpath("Whos_On_First")
        self.memory: Path = self.single_modules.joinpath("Memory")
        self.morse_code: Path = self.single_modules.joinpath("Morse_code")
        self.venn: Path = self.single_modules.joinpath("Venn")
        self.wire_sequence: Path = self.single_modules.joinpath("Wire_Sequence")
        self.maze: Path = self.single_modules.joinpath("Maze")
        self.password: Path = self.single_modules.joinpath("Password")
        self.needy_vent_gas: Path = self.single_modules.joinpath("Needy_Vent_Gas")
        self.needy_capacitor: Path = self.single_modules.joinpath("Needy_Capacitor")
        self.needy_knob: Path = self.single_modules.joinpath("Needy_Knob")

    def delete(self) -> None:
        """Clean up the seed paths."""
        shutil.rmtree(self.bomb_states, ignore_errors=True)
        shutil.rmtree(self.single_modules, ignore_errors=True)
        shutil.rmtree(self.repeated_modules_2, ignore_errors=True)
        shutil.rmtree(self.repeated_modules_5, ignore_errors=True)
        shutil.rmtree(self.multiple_modules_2, ignore_errors=True)
        shutil.rmtree(self.multiple_modules_2_front, ignore_errors=True)
        shutil.rmtree(self.multiple_modules_n, ignore_errors=True)

    def create(self) -> None:
        self.bomb_states.mkdir(parents=True, exist_ok=True)
        self.single_modules.mkdir(parents=True, exist_ok=True)

        self.repeated_modules_2.mkdir(parents=True, exist_ok=True)
        self.repeated_modules_5.mkdir(parents=True, exist_ok=True)
        self.multiple_modules_2.mkdir(parents=True, exist_ok=True)
        self.multiple_modules_2_front.mkdir(parents=True, exist_ok=True)
        self.multiple_modules_n.mkdir(parents=True, exist_ok=True)

        self.wires.mkdir(parents=True, exist_ok=True)
        self.big_button.mkdir(parents=True, exist_ok=True)
        self.keypad.mkdir(parents=True, exist_ok=True)
        self.simon.mkdir(parents=True, exist_ok=True)
        self.whose_on_first.mkdir(parents=True, exist_ok=True)
        self.memory.mkdir(parents=True, exist_ok=True)
        self.morse_code.mkdir(parents=True, exist_ok=True)
        self.venn.mkdir(parents=True, exist_ok=True)
        self.wire_sequence.mkdir(parents=True, exist_ok=True)
        self.maze.mkdir(parents=True, exist_ok=True)
        self.password.mkdir(parents=True, exist_ok=True)
        self.needy_vent_gas.mkdir(parents=True, exist_ok=True)
        self.needy_capacitor.mkdir(parents=True, exist_ok=True)
        self.needy_knob.mkdir(parents=True, exist_ok=True)


class GameClientManager:
    """Manages multiple game clients for parallel operations."""

    def __init__(self, num_clients: int = 3):
        self.num_clients = num_clients
        self.clients: list[KtaneClient] = []
        self.game_processes = []
        self.client_urls: list[str] = []
        self.client_locks: list[asyncio.Lock] = []

        # Register cleanup handler to ensure processes are terminated on exit
        atexit.register(self._cleanup_on_exit)

    def _cleanup_on_exit(self):
        """Cleanup handler that runs when the program exits."""
        for process in self.game_processes:
            with suppress(Exception):
                process.terminate()

        logger.info("Terminated all game processes on exit")

    async def initialize(self):
        """Initialize all game clients."""
        for _ in range(self.num_clients):
            game_url = await self.spawn_game()
            self.client_urls.append(game_url)
            client = KtaneClient(url=game_url)
            self.clients.append(client)
            # Create a lock for each client to ensure sequential processing
            self.client_locks.append(asyncio.Lock())

            # Wait for client to be ready
            # time_until_retry = 5
            # while not await client.healthcheck():
            #     logger.warning("Waiting for server to start")
            #     await asyncio.sleep(1)

        logger.info(f"Initialized {len(self.clients)} game clients")
        return self.clients

    async def spawn_game(self) -> str:
        """Spawn a game instance and return its URL."""
        game_server_port = get_available_port()
        logger.info("Starting `KTANE` (as subprocess)", port=game_server_port)
        game_process = await anyio.open_process(
            cwd=get_executable_path().parent,
            command=[get_executable_path()],
            env={"port": str(game_server_port)} | os.environ.copy(),
        )
        self.game_processes.append(game_process)
        return f"http://localhost:{game_server_port}"

    async def cleanup(self):
        """Clean up all game processes."""
        for client in self.clients:
            await client.__aexit__()

        for process in self.game_processes:
            try:
                process.terminate()
                await process.wait()
            except Exception:
                logger.exception("Error terminating process")

        self.clients = []
        self.game_processes = []
        self.client_urls = []
        self.client_locks = []

    async def process_mission(self, client_index: int, mission_func, *args, **kwargs):
        """Process a mission with a specific client, ensuring sequential execution."""
        client = self.clients[client_index]
        lock = self.client_locks[client_index]

        # Acquire the lock to ensure only one mission is processed at a time by this client
        async with lock:
            logger.debug(f"Client {client_index} processing mission")
            result = await mission_func(client, *args, **kwargs)
            logger.debug(f"Client {client_index} completed mission")
            return result


async def run_seed_gathering_process(
    seed: int, client_manager: GameClientManager, seed_paths: SeedPaths
) -> None:
    """Run the seed gathering process."""
    logger.info(f"Processing seed: {seed}")

    # Step 1: Update the seed in the configuration file
    # config_path = paths.configs / "experiment_generator.yaml"
    # config = OmegaConf.load(config_path)
    # config.mission_generator.seed = seed
    # OmegaConf.save(config, config_path)

    # Step 2: Run the experiment generation script
    python_executable = sys.executable
    process = await asyncio.create_subprocess_exec(
        python_executable,
        str(entrypoints / "generate_experiments.py"),
        "-m",
        "experiment=e1_1,e2,e3,e4_1,e4_2,e5_1,e5_2,e5_3",
        f"mission_generator.seed={seed}",
    )
    stdout, stderr = await process.communicate()

    logger.info(f"Experiment generation completed for seed {seed}")

    # Step 3: Run the difference rating tests
    difference_rating = await get_seed_difference_rating(client_manager, seed_paths=seed_paths)
    if difference_rating is None:
        logger.warning(f"Seed {seed} failed to generate missions.")
        return
    # write the seed and difference rating to a file
    with Path.open(seed_differences_path / f"seed_{seed}_differences.json", "w") as seed_file:
        json.dump(difference_rating, seed_file)


async def main(num_clients: int = 3) -> None:
    """Run to get the seed with best difference rating."""
    # Initialize client manager with desired number of clients
    client_manager = GameClientManager(num_clients=num_clients)

    completed = [int(path.stem.split("_")[1]) for path in seed_differences_path.glob("*.json")]
    seed_range = list(range(SEED_MIN, SEED_MAX))
    seed_range = [seed for seed in seed_range if seed not in completed]
    logger.info(f"Seeds to process: {seed_range}")

    if seed_range:
        await client_manager.initialize()
    try:
        for seed in seed_range:
            seed_paths = SeedPaths(seed, all_bomb_states)
            for directory in [seed_paths.bomb_states, paths.experiments, unique_experiments]:
                if directory.exists():
                    shutil.rmtree(directory)
            seed_paths.create()
            await run_seed_gathering_process(seed, client_manager, seed_paths)
            logger.info(f"Completed processing seed {seed}")
    finally:
        top_seeds = rank_seeds(seed_differences_path)[:3]  # Get the top 3 seeds
        logger.info("Top 3 seeds based on average difference ratings:")
        for rank, (seed, average) in enumerate(top_seeds, start=1):
            logger.info(f"Rank {rank}: Seed {seed}, Average Difference: {average:.2f}")
        # Clean up all game clients
        await client_manager.cleanup()


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


async def get_seed_difference_rating(
    client_manager: GameClientManager, seed_paths: SeedPaths
) -> list[float] | None:
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
    }

    # Put missions into correct lists
    for mission_spec, condition in unique_missions:
        mission_spec.time_scale = 5.0
        if condition == "single_module":
            component: KtaneComponent = mission_spec.components[0]  # Extract the component
            _ = mission_specs["single_module"][component].append(mission_spec)  # pyright: ignore[reportCallIssue, reportArgumentType]
        else:
            _ = mission_specs[condition].append(mission_spec)  # pyright: ignore[reportAttributeAccessIssue]

    # Process missions sequentially for each client
    await save_state_sequential(
        "multiple_modules_2",
        seed_paths.multiple_modules_2,
        client_manager,
        mission_specs["multiple_modules_2"],  # pyright: ignore[reportArgumentType]
    )
    if (
        mission_specs["multiple_modules_2"]
        and check_modules_on_both_sides(seed_paths.multiple_modules_2) is None
    ):
        logger.error("Bomb has modules only on one side")
        return None

    await save_state_sequential(
        "multiple_modules_n",
        seed_paths.multiple_modules_n,
        client_manager,
        mission_specs["multiple_modules_n"],  # pyright: ignore[reportArgumentType]
    )
    if (
        mission_specs["multiple_modules_n"]
        and check_modules_on_both_sides(seed_paths.multiple_modules_n) is None
    ):
        logger.error("Bomb has modules only on one side")
        return None

    await save_single_module_state_sequential(
        client_manager,
        mission_specs["single_module"],
        single_module_path=seed_paths.single_modules,
    )  # pyright: ignore[reportArgumentType]

    if mission_specs["single_module"] and not check_valid_morse_code_modules(
        seed_paths.morse_code
    ):
        logger.error("MorseCode module starts with the same frequency.")
        return None

    await save_state_sequential(
        "repeated_modules_2",
        seed_paths.repeated_modules_2,
        client_manager,
        mission_specs["repeated_modules_2"],  # pyright: ignore[reportArgumentType]
    )

    await save_state_sequential(
        "repeated_modules_5",
        seed_paths.repeated_modules_5,
        client_manager,
        mission_specs["repeated_modules_5"],  # pyright: ignore[reportArgumentType]
    )

    await save_state_sequential(
        "multiple_modules_2_front",
        seed_paths.multiple_modules_2_front,
        client_manager,
        mission_specs["multiple_modules_2_front"],  # pyright: ignore[reportArgumentType]
    )

    seed_difference_rating = []

    logger.info("removing unneeded info from .json files")
    process_directory(seed_paths.bomb_states)

    logger.info("checking if single module bombs are different enough")
    seed_difference_rating.append(single_module_difference(seed_paths.single_modules))

    logger.info("checking if repeated modules 2 bombs are different enough")
    seed_difference_rating.append(
        (
            intra_bomb_difference(seed_paths.repeated_modules_2),
            inter_bomb_difference(seed_paths.repeated_modules_2),
        )
    )
    logger.info("checking if repeated modules 5 bombs are different enough")
    seed_difference_rating.append(
        (
            intra_bomb_difference(seed_paths.repeated_modules_5),
            inter_bomb_difference(seed_paths.repeated_modules_5),
        )
    )
    logger.info("checking if multiple modules 2 front bombs are different enough")
    seed_difference_rating.append(intra_bomb_difference(seed_paths.multiple_modules_2_front))
    logger.info("checking if multiple modules 2 bombs are different enough")
    seed_difference_rating.append(intra_bomb_difference(seed_paths.multiple_modules_2))
    logger.info("checking if multiple modules n bombs are different enough")
    seed_difference_rating.append(
        (
            intra_bomb_difference(seed_paths.multiple_modules_n),
            inter_bomb_difference(seed_paths.multiple_modules_n),
        )
    )

    return seed_difference_rating


async def save_state_sequential(
    condition: str,
    path: Path,
    client_manager: GameClientManager,
    mission_specs: list[KtaneMissionSpec],
) -> None:
    """Save bomb states sequentially across multiple clients."""
    if not mission_specs:
        logger.warning("No missions to process", condition=condition)
        return

    # Create tasks for each mission, distributing them across clients
    tasks = []
    for i, mission_spec in enumerate(mission_specs):
        # Use round-robin to distribute work
        client_index = i % len(client_manager.clients)
        # Create a task that will wait for its turn with the client
        tasks.append(
            client_manager.process_mission(
                client_index, process_mission_with_client, path, mission_spec
            )
        )

    # Run tasks concurrently, but each client will process its missions sequentially
    await tqdm.gather(*tasks, desc=f"Processing {condition}", total=len(tasks))


async def save_single_module_state_sequential(
    client_manager: GameClientManager,
    mission_specs: dict[KtaneComponent, list[KtaneMissionSpec]],
    single_module_path: Path,
) -> None:
    """Save single module bomb states sequentially across multiple clients."""
    tasks = []
    mission_count = 0

    for component, component_missions in mission_specs.items():
        for bomb in component_missions:
            # Use round-robin to distribute work
            client_index = mission_count % len(client_manager.clients)
            # Create a task that will wait for its turn with the client
            tasks.append(
                client_manager.process_mission(
                    client_index,
                    process_single_module_mission,
                    single_module_path / component.name,
                    bomb,
                )
            )
            mission_count += 1

    # Run tasks concurrently, but each client will process its missions sequentially
    await tqdm.gather(*tasks, desc="Processing single module", total=len(tasks))


async def process_mission_with_client(
    client: KtaneClient, path: Path, mission_spec: KtaneMissionSpec
) -> None:
    """Process a single mission with a client."""
    bomb_state = await get_bomb_details(client, mission_spec)
    save(path, mission_spec.seed, mission_spec.components, bomb_state)


async def process_single_module_mission(
    client: KtaneClient, path: Path, bomb: KtaneMissionSpec
) -> None:
    """Process a single module mission with a client."""
    bomb_state = await get_bomb_details(client, bomb)
    save(path, bomb.seed, bomb.components, bomb_state)


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
    all_bombs = list(path.rglob("*.json"))
    for bomb in all_bombs:
        modules = json.loads(bomb.read_text()).get("modules", [])
        has_front = any(module.get("onFront") for module in modules)
        has_back = any(not module.get("onFront") for module in modules)
        if not has_front and not has_back:
            logger.error("Bomb has modules only on one side")
            return None
        logger.debug("Bomb has modules on both sides")
    return 1


def check_valid_morse_code_modules(morse_code_path: Path) -> bool:
    """Ensure morse code is different."""
    all_bomb_paths = list(morse_code_path.rglob("*.json"))
    all_bombs = [json.loads(bomb_path.read_text()) for bomb_path in all_bomb_paths]
    all_morse_modules = [module for modules in all_bombs for module in modules["modules"]]
    for module in all_morse_modules:
        if module["currentFrequency"] == module["correctFrequency"]:
            logger.error("MorseCode module starts with the same frequency.")
            return False
    return True


def save(path: Path, seed: int, modules: list[KtaneComponent], bomb_state: dict[str, Any]) -> None:
    """Saves the bomb state to a file."""
    file_name = str(seed) + "".join(f"_{component.name}" for component in modules)
    file_save = path.joinpath(file_name).with_suffix(".json").write_text(json.dumps(bomb_state))
    assert file_save > 0


def process_directory(bomb_states: Path) -> None:
    """Recursively process all .json files in a directory and its subdirectories."""
    for json_file in bomb_states.rglob("*.json"):  # Recursively find all .json files
        dump_unneeded_info(json_file)


def remove_keys_recursively(data, keys_to_remove: list[str]) -> None:
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
        # "currentFrequency",
        "solveProgress",
        "panel",
        "stripColor",
        "name",
        "isCut",
    ]
    del data["timerModule"]["secondsRemaining"]

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


def count_unique_attributes(data1, data2) -> int:
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


def single_module_difference(single_modules_dir: Path) -> float:
    """Checks if the bombs used in the experiment are different enough."""
    avg_difference = []
    for folder in single_modules_dir.iterdir():
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


async def get_bomb_details(client: KtaneClient, mission_spec: KtaneMissionSpec) -> dict[str, Any]:
    """Starts a game and collects the BombState for each mission."""
    while not await client.healthcheck():
        logger.warning("Waiting for server to start")
        await asyncio.sleep(1)

    await until(get_value=client.gamestate, target=GameState.main_menu)

    _ = await client.start_mission(mission_spec)

    # while not mission_state:
    #     logger.info(f"Game state: {client.game_state()}", client=client.url)
    #     await asyncio.sleep(4)
    #     tried_to_start += 1
    #     if tried_to_start > time_until_retry:
    #         logger.warning("Waiting for mission to start")
    #         if client.game_state() == GameState.game_ended:
    #             logger.info("Game ended, restarting mission")
    #             await client.reset()

    #         mission_state = await client.start_mission(mission_spec)
    #         tried_to_start = 0

    await asyncio.sleep(3)

    # Retrieve the bomb state
    await until(get_value=client.gamestate, target=GameState.lights_on)
    await asyncio.sleep(1)
    bomb_state = await client.client.get("/state")
    bomb_state = bomb_state.json()
    assert bomb_state is not None

    await until(get_value=client.gamestate, target=GameState.lights_on)
    await asyncio.sleep(1)

    # Reset the game after processing
    _ = await client.reset()
    await until(get_value=client.gamestate, target=GameState.main_menu)

    return bomb_state


if __name__ == "__main__":
    asyncio.run(main(num_clients=10))
