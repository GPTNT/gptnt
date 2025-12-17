from dataclasses import dataclass

import logfire
import structlog
from pydantic_ai import BinaryContent

from gptnt.ktane.client import RawObservationFrames
from gptnt.ktane.state.bomb import BombState
from gptnt.players.ai.message_history import AgentMessageInput
from gptnt.players.metrics.recorder import ExperimentPlayerRecorder
from gptnt.players.observation_handler import ObservationHandler
from gptnt.players.specification import PlayerCapabilities, PlayerProtocol
from gptnt.prompts.manual import load_manual_as_prompt

logger = structlog.get_logger()


@dataclass(kw_only=True)
class AgentInputBuilder:
    """Build inputs for the agent.

    This class is used to build the input for the agents from all the different sources we have.
    """

    capabilities: PlayerCapabilities
    protocol: PlayerProtocol

    observation_handler: ObservationHandler

    recorder: ExperimentPlayerRecorder

    @logfire.instrument(
        "Build agent input", extract_args=["messages", "bomb_state", "is_message_history_empty"]
    )
    async def build_agent_input(
        self,
        *,
        messages: str | None,
        raw_frames: RawObservationFrames | None,
        bomb_state: BombState | None,
        is_message_history_empty: bool,
    ) -> AgentMessageInput:
        """Build the input for the agent."""
        agent_input = []

        # 1. Do we want to include the manual? Only if first message and we want it.
        if self.protocol.include_manual and is_message_history_empty:
            logger.debug("Loading manual as prompt")
            agent_input.extend(
                load_manual_as_prompt(
                    desired_image_dimensions=self.capabilities.desired_image_dimensions
                )
            )

        # 2. Pull messages. This should only happen if we are not playing alone (and messages is
        #    not None/empty)
        if not self.protocol.is_playing_alone and messages:
            logger.debug("Adding messages", messages=messages)
            agent_input.append(messages)

        # 3. Add observations if we are the defuser
        if self.protocol.role == "defuser":
            with logfire.span("Adding observations to defuser input"):
                assert raw_frames is not None, "Raw frames must be provided for defuser protocol"
                assert bomb_state is not None, "Bomb state must be provided for defuser protocol"
                logger.debug("Preparing frames")
                observations = await self._prepare_frames(
                    raw_frames=raw_frames, bomb_state=bomb_state
                )
                agent_input.extend(observations)

        return agent_input

    @logfire.instrument("Prepare frames", extract_args=["bomb_state"])
    async def _prepare_frames(
        self, *, raw_frames: RawObservationFrames, bomb_state: BombState
    ) -> list[BinaryContent]:
        """Prepare frames from the game."""
        num_frames_to_use = (
            self.capabilities.max_observation_window_length
            if bomb_state.view_needs_multiple_frames
            else 1
        )
        observation = self.observation_handler.handle_new_observation(
            frames=raw_frames.frames,
            segmentation=raw_frames.segmentation,
            bomb_state=bomb_state,
            num_frames_to_use=num_frames_to_use,
        )

        # Separate to below where we don't include the final frame, here we want to track it so
        # we can make sure the segmentation mask aligns properly too. Hence why this is
        # indexed differently
        await self.recorder.store_step_context(
            bomb_state=bomb_state,
            frames=observation.frames[-num_frames_to_use:],
            segm_mask=observation.segm_mask,
            som_image=observation.som_image,
        )

        observations = [
            *[
                BinaryContent(data=frame, media_type="image/png")
                # Get the last `num_frames_to_use` frames, but not the last one in the list since
                # we want to replace it with the SoM image
                for frame in observation.frames[-num_frames_to_use:-1]
            ],
            BinaryContent(data=observation.som_image, media_type="image/png"),
        ]
        return observations
