import asyncio
import atexit
import json
import os
import re
from contextlib import suppress
from typing import TYPE_CHECKING

import anyio
import structlog
import whenever

from gptnt.common.async_ops import until
from gptnt.common.logger import configure_logging
from gptnt.common.paths import Paths
from gptnt.common.servers import get_available_port
from gptnt.ktane.actions import GameActionType, KtaneBaseAction
from gptnt.ktane.client import KtaneClient
from gptnt.ktane.executable import get_executable_path
from gptnt.ktane.game_settings import KtaneSettings
from gptnt.ktane.mission_spec import KtaneMissionSpec
from gptnt.ktane.state.bomb import BombState
from gptnt.ktane.state.game import GameState
from gptnt.ktane.state.modules import KtaneComponent
from gptnt.ktane.state.widget import SerialWidgetState
from gptnt.processors.image_resizer import ImageResizer
from gptnt.processors.labels.drawing import AnnotationBackgroundParams, AnnotationTextParams
from gptnt.processors.set_of_marks import MaskDrawingParams, SetOfMarksHandler

if TYPE_CHECKING:
    from anyio.abc import Process


configure_logging()

logger = structlog.get_logger()

paths = Paths()

# Define set of marks specs (copied from _defuser_som.yaml)
SET_OF_MARKS_PAINTER = SetOfMarksHandler(
    annotation_text_params=AnnotationTextParams(
        font=2, font_scale=0.7, thickness=1, space_between_boxes=2
    ),
    annotation_background_params=AnnotationBackgroundParams(padding=3, alpha=1),
    mask_drawing_params=MaskDrawingParams(
        mask_thickness=1, soft_mask_alpha=0.1, bw_outside_mask=False, mask_highlight_size=None
    ),
    add_labels=True,
    add_mask_outline=True,
    mark_type="alphabet",
)

# Define image resizer specs (copied from _defuser.yaml)
IMAGE_RESIZER = ImageResizer(target_width=512, target_height=512)


class SimonSaysDefuserManager:
    """Manages the game client for the simon says defuser."""

    def __init__(self) -> None:
        self.client: KtaneClient = None
        self.game_process: Process = None
        self.client_url: str = None

        # Register cleanup handler to ensure processes are terminated on exit
        atexit.register(self._cleanup_on_exit)

    def _cleanup_on_exit(self):
        """Cleanup handler that runs when the program exits."""
        with suppress(Exception):
            self.game_process.terminate()

        logger.info("Terminated all game processes on exit")

    async def initialize(self) -> None:
        """Initialize game clients."""
        game_url = await self.spawn_game()
        self.client_url = game_url
        self.client = KtaneClient(
            url=game_url, set_of_marks_painter=SET_OF_MARKS_PAINTER, image_resizer=IMAGE_RESIZER
        )

    async def spawn_game(self) -> str:
        """Spawn a game instance and return its URL."""
        game_server_port = get_available_port()
        logger.info("Starting `KTANE` (as subprocess)", port=game_server_port)
        game_process = await anyio.open_process(
            cwd=get_executable_path().parent,
            command=[get_executable_path()],
            env={"port": str(game_server_port)} | os.environ.copy(),
        )
        self.game_process = game_process
        return f"http://localhost:{game_server_port}"

    async def cleanup(self) -> None:
        """Clean up game processes."""
        await self.client.__aexit__()

        try:
            self.game_process.terminate()
            await self.game_process.wait()
        except Exception:
            logger.exception("Error terminating process")

        self.clients = None
        self.game_processes = None
        self.client_urls = None

    async def start_simon_says_mission(self, seed) -> str:
        """Start simon says mission."""
        while not await self.client.healthcheck():
            logger.warning("Waiting for server to start")
            await asyncio.sleep(1)

        await until(get_value=self.client.gamestate, target=GameState.main_menu)

        mission_spec = KtaneMissionSpec(
            seed=seed, time_limit=90, components=[KtaneComponent.simon], optional_widgets=0
        )
        _ = await self.client.start_mission(mission_spec)


def get_button_to_press(*, flash_color: str, serial_has_vowel: bool, strikes: int) -> str:
    """Determine which button to press based on the flashed color, serial number, and strikes.

    Args:
        flash_color (str): The color that flashed ('red', 'blue', 'green', or 'yellow')
        serial_has_vowel (bool): Whether the serial number contains a vowel
        strikes (int): The number of strikes (0, 1, or 2+)

    Returns:
        str: The color of the button to press
    """
    print(f"number of strikes: {strikes}")  # noqa: T201
    # Define the mapping tables based on the manual
    if serial_has_vowel:
        # Serial number contains a vowel
        if strikes == 0:
            mapping = {"red": "blue", "blue": "red", "green": "yellow", "yellow": "green"}
        elif strikes == 1:
            mapping = {"red": "yellow", "blue": "green", "green": "blue", "yellow": "red"}
        else:  # 2+ strikes
            mapping = {"red": "green", "blue": "red", "green": "yellow", "yellow": "blue"}
    else:
        # Serial number does not contain a vowel
        if strikes == 0:
            mapping = {"red": "blue", "blue": "yellow", "green": "green", "yellow": "red"}
        elif strikes == 1:
            mapping = {"red": "red", "blue": "blue", "green": "yellow", "yellow": "green"}
        else:  # 2+ strikes
            mapping = {"red": "yellow", "blue": "green", "green": "blue", "yellow": "red"}

    return mapping[flash_color]


def color_to_som(color: str) -> str:
    """Convert a color to its corresponding som letter."""
    color_map = {"blue": "A", "red": "B", "yellow": "C", "green": "D"}
    return color_map[color]


def check_serial_has_vowel(bomb_state: BombState) -> bool:
    """Check if the serial number in the bomb state contains a vowel."""

    for widget in bomb_state.widgets:
        if isinstance(widget, SerialWidgetState):
            serial = widget.serial_number.upper()
            return any(vowel in serial for vowel in "AEIOU")

    raise ValueError("No Serial Number widget found in the bomb state.")


async def update_som(*, ktane_client: KtaneClient, should_save_images: bool) -> None:
    """Update the som for the current bomb state."""
    current_bomb_state = await ktane_client.get_state()

    # get observation frames
    frames, segm_mask, som_image = await ktane_client.get_observation_frames()

    if should_save_images:
        save_name = f"bomb_{whenever.Instant.now()}"
        sanitised_save_name = re.sub(r"[:.]", "_", save_name)

        save_dir = paths.output.joinpath("simon_observation_dataset", sanitised_save_name)
        save_dir.mkdir(parents=True, exist_ok=True)

        for index, frame in enumerate(frames, start=1):
            screenshot_path = save_dir.joinpath(f"screenshot{index}.png")
            _ = screenshot_path.write_bytes(frame)

        _ = save_dir.joinpath("segmentation.png").write_bytes(segm_mask)
        _ = save_dir.joinpath("som_image.png").write_bytes(som_image)

        bomb_state_path = save_dir.joinpath("state.json")
        with bomb_state_path.open("w", encoding="utf-8") as bomb_state_file:
            json.dump(
                obj=current_bomb_state.model_dump(mode="json", by_alias=True),
                fp=bomb_state_file,
                indent=4,
            )


async def observe_sequence(*, ktane_client: KtaneClient, should_save_images: bool) -> None:
    """Zoom out, zoom in (resets the sequence), saves observations for a few seconds, and saves
    them."""
    # zoom out
    zoom_out_action = KtaneBaseAction[str](action=GameActionType.zoom_out)
    await ktane_client.send_action(action=zoom_out_action)
    await asyncio.sleep(0.5)

    await update_som(ktane_client=ktane_client, should_save_images=False)

    # zoom in
    select_module_action = KtaneBaseAction[str](action=GameActionType.click_release, location="A")
    await ktane_client.send_action(action=select_module_action)

    # wait for beep to start
    await asyncio.sleep(1)

    # wait for beep sequence to finish
    await asyncio.sleep(4)

    # get observations
    await update_som(ktane_client=ktane_client, should_save_images=should_save_images)


async def play_simon_says(*, ktane_client: KtaneClient, should_save_images) -> None:
    current_bomb_state = await ktane_client.get_state()
    simon_module = current_bomb_state.modules[0]
    serial_has_vowel = check_serial_has_vowel(bomb_state=current_bomb_state)

    # flip bomb if needed
    if simon_module.on_front != (current_bomb_state.bomb_side == "front"):
        print("Simon Says module is on the front side of the bomb.")  # noqa: T201
        flip_action = KtaneBaseAction[str](action=GameActionType.flip)
        await ktane_client.send_action(action=flip_action)

    # await asyncio.sleep(1)
    await update_som(ktane_client=ktane_client, should_save_images=False)
    # await asyncio.sleep(1)

    # select simon says module (assuming it is the only module)
    select_module_action = KtaneBaseAction[str](action=GameActionType.click_release, location="A")
    await ktane_client.send_action(action=select_module_action)

    await asyncio.sleep(1)

    current_beep_count = 0

    while True:
        current_beep_count += 1

        # watch the new sequence
        await observe_sequence(ktane_client=ktane_client, should_save_images=should_save_images)

        current_bomb_state = await ktane_client.get_state()
        simon_module = current_bomb_state.modules[0]
        strikes = current_bomb_state.current_strikes

        if simon_module.is_solved:
            break

        # await update_som(ktane_client=ktane_client, should_save_images=should_save_images)

        # figure out which buttons to press
        sequence_to_replicate = simon_module.beep_sequence[:current_beep_count]
        press_sequence = [
            get_button_to_press(
                flash_color=color, serial_has_vowel=serial_has_vowel, strikes=strikes
            )
            for color in sequence_to_replicate
        ]

        # press the buttons
        for color, press_color in zip(sequence_to_replicate, press_sequence, strict=False):
            label_to_press = color_to_som(press_color)
            print(f"Flash: {color} -> Press: {press_color} (SOM: {label_to_press})")  # noqa: T201

            press_button_action = KtaneBaseAction[str](
                action=GameActionType.click_release, location=label_to_press
            )
            await ktane_client.send_action(action=press_button_action)
            await asyncio.sleep(0.5)


async def main() -> None:
    # update environment variables
    ktane_settings = KtaneSettings()
    ktane_settings.update_environment_variables()

    # start ktane and run a simon says mission
    client_manager = SimonSaysDefuserManager()
    await client_manager.initialize()
    await client_manager.start_simon_says_mission(seed=123)

    # wait for the bomb state to be available
    while await client_manager.client.get_state() is None:  # noqa: ASYNC110
        await asyncio.sleep(1)

    # play simon says
    await play_simon_says(ktane_client=client_manager.client, should_save_images=True)


if __name__ == "__main__":
    asyncio.run(main())
