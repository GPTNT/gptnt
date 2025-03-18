from enum import Enum

from httpx import QueryParams
from pydantic import BaseModel, Field


class KtaneComponent(Enum):
    """Enum representing valid KTANE components."""

    wires = "Wires"
    big_button = "BigButton"
    simon_says = "SimonSays"
    key_pad = "KeyPad"


class KtaneMissionSpec(BaseModel):
    """Configuration for a mission in KTANE."""

    seed: int = Field(ge=0, description="Random seed for mission generation")
    time_limit: int = Field(ge=10, le=600, alias="timeLimit", description="Time limit in seconds")  # noqa: WPS432
    num_strikes: int = Field(
        ge=1, le=5, alias="numStrikes", description="Allowed mistakes before failure"
    )
    needy_time: int = Field(
        ge=10,
        le=180,  # noqa: WPS432
        alias="needyTime",
        description="Time before needy modules activate",
    )
    is_front: bool = Field(alias="isFront", description="Whether bomb is front-facing")
    opt_widgets: int = Field(
        ge=0, le=10, alias="optWidgets", description="Number of optional widgets"
    )
    components: list[KtaneComponent] = Field(
        description="List of required components in the mission"
    )
    time_scale: float = Field(
        ge=0.1,
        le=10.0,  # noqa: WPS432
        alias="timeScale",
        description="Time scale multiplier",
    )
    time_step_size: int = Field(
        ge=50,  # noqa: WPS432
        le=500,  # noqa: WPS432
        alias="timeStepSize",
        description="Step size in milliseconds",
    )

    def to_query_params(self) -> QueryParams:
        """Converts the mission spec into a query parameter string for API requests."""
        specification_dict = self.dict(by_alias=True)
        # Fix the enums for the components which is what the API wants
        specification_dict["components"] = (
            ",".join(component.value for component in specification_dict["components"]),
        )
        return QueryParams(specification_dict)


class KtaneAction(BaseModel):
    """Action to perform in the game."""
