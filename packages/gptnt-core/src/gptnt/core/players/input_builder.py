from dataclasses import dataclass

import logfire
import structlog
from pydantic_ai import BinaryContent

from gptnt.core.ktane.client import FrameBuffer
from gptnt.core.ktane.state.bomb import BombState
from gptnt.core.players.observation_handler import ObservationHandler
from gptnt.core.players.recording import StepContextRecorder
from gptnt.core.specification import PlayerCapabilities, PlayerProtocol

logger = structlog.get_logger()

type AgentMessageInput = str | list[str | BinaryContent]


@dataclass(kw_only=True)
class AgentInputBuilder:
    """Build inputs for the agent.

    This class is used to build the input for the agents from all the different sources we have.
    """

    capabilities: PlayerCapabilities
    protocol: PlayerProtocol

    observation_handler: ObservationHandler

    recorder: StepContextRecorder | None

    @logfire.instrument("Build agent input", extract_args=["messages", "bomb_state"])
    async def build_agent_input(
        self,
        *,
        messages: str | None,
        frame_buffer: FrameBuffer | None,
        bomb_state: BombState | None,
    ) -> AgentMessageInput:
        """Build the input for the agent."""
        agent_input = []

        # 2. Pull messages. This should only happen if we are not playing alone (and messages is
        #    not None/empty)
        if not self.protocol.is_playing_alone and messages:
            logger.debug("Adding messages", messages=messages)
            agent_input.append(messages)

        # 3. Add observations if we are the defuser
        if self.protocol.role == "defuser":
            with logfire.span("Adding observations to defuser input"):
                assert frame_buffer is not None, (
                    "Frame buffer must be provided for defuser protocol"
                )
                assert bomb_state is not None, "Bomb state must be provided for defuser protocol"
                observations = await self._prepare_frames(
                    frame_buffer=frame_buffer, bomb_state=bomb_state
                )
                agent_input.extend(observations)

        return agent_input

    @logfire.instrument("Prepare frames", extract_args=["bomb_state"])
    async def _prepare_frames(
        self, *, frame_buffer: FrameBuffer, bomb_state: BombState
    ) -> list[BinaryContent]:
        """Prepare frames from the game."""
        num_frames_to_use = (
            self.capabilities.max_observations_per_request
            if bomb_state.view_needs_multiple_frames
            else 1
        )
        observation = self.observation_handler.handle_new_observation(
            frame_buffer=frame_buffer, bomb_state=bomb_state, num_frames_to_use=num_frames_to_use
        )

        # Separate to below where we don't include the final frame, here we want to track it so
        # we can make sure the segmentation mask aligns properly too. Hence why this is
        # indexed differently
        if self.recorder is not None:
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
