import random
from dataclasses import dataclass
from functools import partial

import anyio
import hydra
import orjson
from rich.console import Console
from rich.table import Table
from structlog import get_logger
from whenever import Instant

from gptnt.common.hydra import get_hydra_overrides
from gptnt.common.image_ops import load_observation_from_bytes
from gptnt.common.logger import configure_logging
from gptnt.common.paths import Paths
from gptnt.ktane.actions import GameActionType
from gptnt.ktane.client import FrameBuffer
from gptnt.ktane.manual import KtaneManualPaths
from gptnt.ktane.state.bomb import BombState
from gptnt.players.action_predictor import ActionPredictor
from gptnt.players.history.message_history import MessageHistory
from gptnt.players.input_builder import AgentInputBuilder
from gptnt.players.observation_handler import ObservationHandler
from gptnt.players.specification import PlayerCapabilities, PlayerProtocol
from gptnt.prompts.manual import load_manual_as_prompt
from gptnt.prompts.prompt_cache import PromptCache

console = Console()
logger = get_logger()

paths = Paths()
ktane_manual_paths = KtaneManualPaths()


@dataclass(kw_only=True)
class BoxWarmer:
    """Warmup the box."""

    capabilities: PlayerCapabilities
    observation_handler: ObservationHandler
    action_predictor: ActionPredictor

    async def run_prompt(self, *, protocol: PlayerProtocol) -> None:
        """Run a simple prompt through the model to warm it up."""
        self.action_predictor.configure_for_experiment(
            protocol=protocol,
            message_history=MessageHistory(capabilities=self.capabilities, protocol=protocol),
        )
        input_builder = AgentInputBuilder(
            capabilities=self.capabilities,
            protocol=protocol,
            observation_handler=self.observation_handler,
            recorder=None,
        )
        message = self.generate_message(protocol)
        frame_buffer, bomb_state = self.generate_observations()
        model_input = await input_builder.build_agent_input(
            messages=message, frame_buffer=frame_buffer, bomb_state=bomb_state
        )
        response = await self.action_predictor.send_request_to_agent(message_input=model_input)
        logger.info(
            "Warmup response received",
            output=response.output,
            usage=response.usage,
            raw_output=response.raw_output,
            ai_response_error=response.ai_response_error,
        )

    def generate_message(self, protocol: PlayerProtocol) -> str:
        """Generate a simple message for warming up."""
        match protocol.role:
            case "defuser":
                return random.choice(list(GameActionType)).name
            case "expert":
                return "Tell me what to do."

    def generate_observations(self) -> tuple[FrameBuffer, BombState]:
        """Generate simple observations for warming up."""
        warmup_json = orjson.loads(
            paths.storage.joinpath("fixtures", "defuser_warmup.json").read_bytes()
        )
        bomb_state = BombState.model_validate(warmup_json["bomb_state"])

        obs = warmup_json["observation"]
        raw_frames: list[str] = obs["frames"]
        raw_segm: str | None = obs.get("segm_mask")

        frames = [load_observation_from_bytes(frame) for frame in raw_frames]
        segmentation_mask = load_observation_from_bytes(raw_segm) if raw_segm else None

        frame_buffer = FrameBuffer.from_pil_images(
            frames=frames, segmentation_mask=segmentation_mask
        )

        return frame_buffer, bomb_state


def generate_protocol() -> PlayerProtocol:
    """Generate a protocol for warming up."""
    role = random.choice(["defuser", "expert"])
    is_playing_alone = random.choice([True, False]) if role == "defuser" else False
    return PlayerProtocol(
        role=role,  # pyright: ignore[reportArgumentType]
        communication_style=random.choice(["async", "sync"]),
        is_playing_alone=is_playing_alone,
        include_manual=random.choice([True, False]),
    )


def create_box_warmer(*, hydra_overrides: list[str] | None = None) -> BoxWarmer:
    """Warmup the box."""
    hydra_overrides = hydra_overrides or get_hydra_overrides()
    logger.info("Creating box warmer", hydra_overrides=hydra_overrides)
    with hydra.initialize_config_dir(version_base="1.3", config_dir=str(paths.configs)):
        cfg = hydra.compose(config_name="player.yaml", overrides=hydra_overrides)

    capabilities = hydra.utils.instantiate(cfg.player.capabilities)
    observation_handler = hydra.utils.instantiate(cfg.player.observation_handler)
    action_predictor = hydra.utils.instantiate(cfg.player.action_predictor)
    warmer = BoxWarmer(
        capabilities=capabilities,
        observation_handler=observation_handler,
        action_predictor=action_predictor,
    )

    # Build prompt cache up front
    PromptCache.initialise(
        paths.prompts, ktane_manual_paths.text_dir, ktane_manual_paths.images_small_dir
    )
    _ = load_manual_as_prompt(image_dimensions=capabilities.image_dimensions)

    return warmer


def collate_results(times: list[tuple[PlayerProtocol, float]]) -> None:  # noqa: WPS210
    """Collate time results for the warmup runs."""
    console.rule("Warmup Time Table")
    table_data = [
        {
            "Iteration": idx + 1,
            "Role": protocol.role,
            "Alone": protocol.is_playing_alone,
            "Comm Style": protocol.communication_style,
            "Include Manual": protocol.include_manual,
            "Time (s)": f"{time:.2f}",
        }
        for idx, (protocol, time) in enumerate(times)  # noqa: WPS204
    ]
    table = Table(*list(table_data[0].keys()))
    for row in table_data:
        table.add_row(*[str(value) for value in row.values()])  # noqa: WPS110
    console.print(table)

    average_time = sum(time for _, time in times) / len(times)
    console.print(f"Average warmup time: {average_time} seconds")
    # average defuser warmup time
    defuser_times = [time for protocol, time in times if protocol.role == "defuser"]
    if defuser_times:
        average_defuser_time = sum(defuser_times) / len(defuser_times)
        console.print(f"Average defuser warmup time: {average_defuser_time} seconds")

    # average expert warmup time
    expert_times = [time for protocol, time in times if protocol.role == "expert"]
    if expert_times:
        average_expert_time = sum(expert_times) / len(expert_times)
        console.print(f"Average expert warmup time: {average_expert_time} seconds")

    # defuser with manual
    defuser_manual_times = [
        time for protocol, time in times if protocol.role == "defuser" and protocol.include_manual
    ]
    if defuser_manual_times:
        average_defuser_manual_time = sum(defuser_manual_times) / len(defuser_manual_times)
        console.print(
            f"Average defuser with manual warmup time: {average_defuser_manual_time} seconds"
        )
    # defuser without manual
    defuser_no_manual_times = [
        time
        for protocol, time in times
        if protocol.role == "defuser" and not protocol.include_manual
    ]
    if defuser_no_manual_times:
        average_defuser_no_manual_time = sum(defuser_no_manual_times) / len(
            defuser_no_manual_times
        )
        console.print(
            f"Average defuser without manual warmup time: {average_defuser_no_manual_time} seconds"
        )


if __name__ == "__main__":
    configure_logging()
    warmer = create_box_warmer()

    all_times: list[tuple[PlayerProtocol, float]] = []

    for idx in range(10):
        console.rule(f"Warmup Iteration {idx + 1}")
        protocol = generate_protocol()
        start_time = Instant.now()
        anyio.run(partial(warmer.run_prompt, protocol=protocol))
        end_time = Instant.now()
        duration = end_time - start_time
        logger.info(
            f"Warmup iteration complete ({duration.in_seconds()} seconds)",
            iteration=idx + 1,
            seconds=duration.in_seconds(),
        )
        all_times.append((protocol, duration.in_seconds()))

    collate_results(all_times)
