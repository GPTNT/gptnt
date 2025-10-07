import io
import os

import anyio
import structlog
from PIL import Image

from gptnt.common.async_ops import periodic
from gptnt.common.paths import Paths
from gptnt.common.servers import get_available_port
from gptnt.ktane.actions import GameActionType, KtaneBaseAction
from gptnt.ktane.client import KtaneClient
from gptnt.ktane.executable import get_executable_path
from gptnt.ktane.game_settings import KtaneSettings
from gptnt.ktane.mission_spec import KtaneMissionSpec
from gptnt.ktane.state.game import GameState
from gptnt.ktane.state.modules import KtaneComponent
from gptnt.players.observation_handler import ObservationHandler
from gptnt.processors.labels.drawing import AnnotationBackgroundParams, AnnotationTextParams
from gptnt.processors.set_of_marks import MaskDrawingParams, SetOfMarksHandler
from gptnt.services.game.process_manager import GameProcessManager

logger = structlog.get_logger()

paths = Paths()

SET_OF_MARKS_PAINTER: SetOfMarksHandler = SetOfMarksHandler(
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


class ScreenshotTaker:
    def __init__(self, game_width: int, game_height: int) -> None:
        self.ktane_settings = KtaneSettings(game_width=game_width, game_height=game_height)
        self.game_width = game_width
        self.game_height = game_height
        self.process_manager = GameProcessManager()
        self.ktane_client = KtaneClient(url="")
        self.observation_handler = ObservationHandler(set_of_marks_painter=SET_OF_MARKS_PAINTER)

    async def setup_game(self):
        self.ktane_settings.update_environment_variables()
        self.ktane_settings.create_settings_files()

        self.port = get_available_port()
        env = os.environ.copy()
        env["port"] = str(self.port)

        self.process_manager._port = self.port  # noqa: SLF001
        self.process_manager._process = await anyio.open_process(  # noqa: SLF001
            cwd=get_executable_path().parent, command=[get_executable_path()], env=env
        )

        game_url = f"http://localhost:{self.port}"
        await self.ktane_client.update_url(game_url)

        await self.wait_until(GameState.main_menu)
        logger.info("Game is ready to start mission")

    async def start_mission(self, component: KtaneComponent) -> None:
        self.component = component
        await self.ktane_client.start_mission(
            KtaneMissionSpec(
                seed=1,
                time_limit=500,
                num_strikes_allowed=3,
                components=[component],
                optional_widgets=3,
                force_modules_to_front=True,
            )
        )
        await self.wait_until(GameState.lights_on)
        await anyio.sleep(3)  # wait for the bomb to be picked up

    async def reset(self):
        await self.ktane_client.go_to_main_menu()
        await self.wait_until(GameState.main_menu)

    async def get_observation(self, *, after_action: bool) -> None:
        raw_observation = await self.ktane_client.get_observation_frames()
        bomb_state = await self.ktane_client.get_bomb_state()
        observation = self.observation_handler.handle_new_observation(
            frames=raw_observation.frames,
            segmentation=raw_observation.segmentation,
            bomb_state=bomb_state,
        )
        self._save_image(som_image=observation.som_image, after_action=after_action)

    def _save_image(self, *, som_image: bytes, after_action: bool):
        save_name = (
            f"{self.component}_{self.game_width}.png"
            if not after_action
            else f"{self.component}_{self.game_width}_with_action.png"
        )
        save_dir = paths.output.joinpath("resolution_comparison_dataset")
        save_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = save_dir.joinpath(save_name)

        # image = Image.frombytes("RGB", (self.game_width, self.game_height), som_image)
        image = Image.open(io.BytesIO(som_image))
        if self.game_width != 512 or self.game_height != 512:
            image = image.resize((512, 512), Image.Resampling.LANCZOS)
        image.save(screenshot_path)
        logger.info(f"Saved screenshot to {screenshot_path}")

    async def click_a(self) -> None:
        select_module_action = KtaneBaseAction[str](
            action=GameActionType.click_release, location="A"
        )
        self.observation_handler.convert_to_game_action(action=select_module_action)
        await self.ktane_client.send_action(action=select_module_action)
        await anyio.sleep(3)  # wait for the interaction to complete

    # Helper function for waiting for a game state
    async def wait_until(self, state: GameState) -> None:
        """Wait until the game reaches the given state."""
        async for _ in periodic(1):
            try:
                current_state = await self.ktane_client.get_game_state()
                if current_state == state:
                    return
            except Exception:  # noqa: BLE001
                logger.info("Cannot get state yet")


async def run(components: list[KtaneComponent], resolutions: list[tuple[int, int]]) -> None:
    total_components = len(components)
    total_resolutions = len(resolutions)

    for res_idx, resolution in enumerate(resolutions):
        width, height = resolution

        res_progress = f"{res_idx + 1}/{total_resolutions}"
        logger.info(f"Starting resolution: {width}x{height}. Resolution progress: {res_progress}")

        try:
            ss = ScreenshotTaker(game_width=width, game_height=height)
            logger.info("Setting up the game")
            await ss.setup_game()
            logger.info("Set up done")

            for comp_idx, component in enumerate(components):
                comp_progress = f"{comp_idx + 1}/{total_components}"
                total_experiments = total_components * total_resolutions
                current_experiment = res_idx * total_components + comp_idx + 1
                total_progress = f"{current_experiment}/{total_experiments}"

                logger.info(
                    f"Currently running {component.name} component on resolution {width}x{height}. Component progress: {comp_progress}. Total progress: {total_progress}"
                )

                await ss.start_mission(component=component)
                await ss.get_observation(after_action=False)
                await ss.click_a()
                await ss.get_observation(after_action=True)
                await ss.reset()

            logger.info(
                f"Finished all components for resolution: {width}x{height}. Resolution progress: {res_progress}"
            )

        except Exception:
            logger.exception(f"Oops {width}x{height}.")
            return

        finally:
            await ss.process_manager.terminate()
            logger.info(f"Clean up complete for resolution {width}x{height}.")


if __name__ == "__main__":
    components = [
        KtaneComponent.big_button,
        KtaneComponent.wires,
        KtaneComponent.wire_sequence,
        KtaneComponent.keypad,
        KtaneComponent.maze,
        KtaneComponent.simon,
        KtaneComponent.whos_on_first,
        KtaneComponent.memory,
        KtaneComponent.morse_code,
        KtaneComponent.venn,
        KtaneComponent.password,
    ]

    resolutions = [(640, 480), (512, 512)]

    anyio.run(run, components, resolutions)
