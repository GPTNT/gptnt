from typing import Any, Self

import polars as pl
import wandb
from pydantic import BaseModel, SerializationInfo, TypeAdapter, field_serializer, model_serializer
from structlog import get_logger

from gptnt.common.image_ops import load_observation_from_bytes
from gptnt.ktane.actions import GameActionTypeWithMagic, KtaneBaseAction
from gptnt.ktane.state.bomb import BombState
from gptnt.ktane.state.modules import KtaneComponent, ModuleStates
from gptnt.ktane.state.widget import WidgetStates
from gptnt.players.actions import (
    DoNothingAction,
    DoNothingActionWithThoughts,
    GameInteractionActionType,
    InteractableLocation,
    SendMessageAction,
    SendMessageActionWithThoughts,
    ThoughtsMixin,
)
from gptnt.players.specification import PlayerRole

_logger = get_logger()


class TimestampMixin(BaseModel):
    """Mixin class to add a timestamp to the model."""

    timestamp: float


class ActionMetric(
    KtaneBaseAction[GameActionTypeWithMagic, InteractableLocation], ThoughtsMixin, TimestampMixin
):
    """Action metric class for observability logging."""

    @classmethod
    def from_action(cls, *, ktane_action: GameInteractionActionType, timestamp: float) -> Self:
        """Create an ActionMetric from an InteractGameAction."""
        thoughts = getattr(ktane_action, "thoughts", None)
        return cls(
            action=ktane_action.action,
            location=ktane_action.location,
            thoughts=thoughts,
            timestamp=timestamp,
        )


class MessageMetric(SendMessageActionWithThoughts, TimestampMixin):
    """SendMessageAction for logging."""

    role: PlayerRole | None

    @classmethod
    def from_action(
        cls,
        *,
        action: SendMessageAction | SendMessageActionWithThoughts,
        role: PlayerRole | None,
        timestamp: float,
    ) -> Self:
        """Create a MessageMetric from an SendMessageAction."""
        thoughts = getattr(action, "thoughts", None)

        return cls(message=action.message, role=role, thoughts=thoughts, timestamp=timestamp)


class DoNothingMetric(DoNothingActionWithThoughts, TimestampMixin):
    """Metric class for do nothing actions."""

    role: PlayerRole | None

    @classmethod
    def from_action(
        cls,
        *,
        action: DoNothingAction | DoNothingActionWithThoughts,
        role: PlayerRole | None,
        timestamp: float,
    ) -> Self:
        """Create a DoNothingMetric from a DoNothingAction."""
        thoughts = getattr(action, "thoughts", None)
        return cls(thoughts=thoughts, role=role, timestamp=timestamp)


class BombStateMetric(BombState, TimestampMixin):
    """Bomb state metric class for observability logging."""

    @classmethod
    def from_bomb_state(cls, *, bomb_state: BombState, timestamp: float) -> Self:
        """Instantiate from a BombState.

        Because BombState is a subclass of this class, we just set the timestamp and pass it in
        because it should work. This is a bit of a hack, but it works.
        """
        return cls.model_validate({**bomb_state.model_dump(), "timestamp": timestamp})

    @classmethod
    def polars_schema_override(cls) -> dict[str, Any]:
        """Override the schema for the polars dataframe to build a consistent table."""
        return {
            "seed": pl.Int32,
            "max_strikes": pl.Int32,
            "strikes": pl.String,
            "is_detonated": pl.Boolean,
            "is_solved": pl.Boolean,
            "is_light_on": pl.Boolean,
            "timer_module": pl.Struct(
                fields={
                    "name": pl.String,
                    "on_front": pl.Boolean,
                    "index": pl.Int32,
                    "seconds_remaining": pl.Float32,
                }
            ),
            "widgets": pl.String,
            "modules": pl.String,
        }

    @field_serializer("modules")
    def serialize_modules(self, modules: list[ModuleStates]) -> str:
        """Serialize the modules to a string."""
        return TypeAdapter(list[ModuleStates]).dump_json(modules).decode("utf-8")

    @field_serializer("widgets")
    def serialize_widgets(self, widgets: list[WidgetStates]) -> str:
        """Serialize the widgets to a string."""
        return TypeAdapter(list[WidgetStates]).dump_json(widgets).decode("utf-8")

    @field_serializer("strikes")
    def serialize_strikes(self, strikes: list[KtaneComponent]) -> str:
        """Serialize the strikes to a string."""
        return TypeAdapter(list[KtaneComponent]).dump_json(strikes).decode("utf-8")


class ObservationMetric(TimestampMixin):
    """Observation metric class for observability logging.

    This class represents an observation in the form of multiple frames (images) instead of a
    singular raw image. Each frame is stored as a byte array. Additional attributes include
    a segmentation mask (`segm_mask`) and a secondary observation metric image (`som_image`).
    """

    frames: list[bytes]
    segm_mask: bytes | None
    som_image: bytes

    @model_serializer(mode="plain")
    def serialize_wandb(self, info: SerializationInfo) -> dict[str, Any]:  # noqa: WPS110
        """Serialize the observation to a WandB image."""
        context = info.context
        if context is None:
            return self.model_dump()
        is_for_wandb = context.get("wandb", False) is not None
        if is_for_wandb:
            # If we are in a wandb context, we need to convert the images to wandb images
            return self._to_wandb_images()
        return self.model_dump()

    def _to_wandb_images(self) -> dict[str, Any]:
        # Convert the images to WandB images
        frames = [
            wandb.Image(
                load_observation_from_bytes(self.frames[frame_index]),
                caption=f"Frame {frame_index}",
            )
            for frame_index in range(len(self.frames))
        ]
        segm_mask = (
            wandb.Image(load_observation_from_bytes(self.segm_mask), caption="Segmentation Mask")
            if self.segm_mask
            else None
        )
        som_image = wandb.Image(load_observation_from_bytes(self.som_image), caption="SoM Image")

        return {
            "frames": frames,
            "segmentation_mask": segm_mask,
            "som_image": som_image,
            "timestamp": self.timestamp,
        }
