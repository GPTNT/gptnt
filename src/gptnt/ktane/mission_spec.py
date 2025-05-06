from typing import cast, override

from httpx import QueryParams
from pydantic import BaseModel, ConfigDict, Field, field_validator

from gptnt.ktane.experiments.time_limits import NEEDS_MULTIPLE_IMAGES
from gptnt.ktane.state.modules import KtaneComponent

MAX_COMPONENTS = 11


class KtaneMissionSpec(BaseModel):
    """Configuration for a mission in KTANE."""

    model_config = ConfigDict(validate_by_name=True, validate_by_alias=True)

    seed: int = Field(ge=0, description="Random seed for mission generation")
    time_limit: int = Field(
        gt=0, serialization_alias="timeLimit", description="Time limit in seconds"
    )
    num_strikes_allowed: int = Field(
        default=3,
        ge=1,
        le=5,
        serialization_alias="numStrikes",
        description="Allowed mistakes before failure",
    )
    components: list[KtaneComponent] = Field(
        max_length=MAX_COMPONENTS, description="List of required components in the mission"
    )
    optional_widgets: int = Field(
        ge=0, le=10, serialization_alias="optWidgets", description="Number of optional widgets"
    )

    needy_time: int = Field(
        default=60,
        gt=0,
        serialization_alias="needyTime",
        description="Time before needy modules activate",
    )
    force_modules_to_front: bool = Field(
        default=False, serialization_alias="isFront", description="Whether bomb is front-facing"
    )
    time_scale: float = Field(
        default=1.0,
        ge=0.1,
        le=10.0,  # noqa: WPS432
        serialization_alias="timeScale",
        description="Time scale multiplier",
    )
    time_step_size: int = Field(
        default=3000,  # noqa: WPS432
        serialization_alias="timeStepSize",
        description="Step size in milliseconds",
    )

    @property
    def requires_multiple_images_per_observation(self) -> bool:
        """Check if the mission requires multiple images per observation."""
        return any(NEEDS_MULTIPLE_IMAGES.get(component, False) for component in self.components)

    @field_validator("components", mode="before")
    @classmethod
    def coerce_components(
        cls,
        components: str | list[str] | list[KtaneComponent],  # noqa: WPS110
    ) -> list[KtaneComponent]:
        """Coerce components to KtaneComponent enum values."""
        if isinstance(components, str):
            components = components.split(",") if "," in components else [components]
            components = [comp.strip().capitalize() for comp in components]

        if all(isinstance(comp, str) for comp in components):
            components = [KtaneComponent(comp) for comp in components]

        return cast("list[KtaneComponent]", components)

    def to_query_params(self) -> QueryParams:
        """Converts the mission spec into a query parameter string for API requests."""
        specification_dict = self.model_dump(by_alias=True)
        # Fix the enums for the components which is what the API wants
        specification_dict["components"] = (
            ",".join(component.value for component in specification_dict["components"]),
        )
        return QueryParams(specification_dict)

    @override
    def __hash__(self) -> int:
        return hash(
            (
                self.seed,
                self.time_limit,
                self.num_strikes_allowed,
                tuple(self.components),
                self.optional_widgets,
                self.needy_time,
                self.force_modules_to_front,
                self.time_scale,
                self.time_step_size,
            )
        )
