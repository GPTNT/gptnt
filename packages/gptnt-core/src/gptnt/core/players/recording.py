from typing import Protocol

from gptnt.core.common.image_ops import PNGBytes
from gptnt.core.ktane.state.bomb import BombState


class StepContextRecorder(Protocol):
    """Structural interface for recording per-step observation context.

    Declared in the player layer so that input building does not depend on the records package. The
    concrete recorder (`ExperimentPlayerRecorder` in `gptnt.experiments`) structurally satisfies
    this protocol.
    """

    async def store_step_context(
        self,
        *,
        bomb_state: BombState,
        frames: list[PNGBytes],
        segm_mask: PNGBytes | None,
        som_image: PNGBytes,
    ) -> None:
        """Store the observation and bomb state context for the current step."""
        ...
