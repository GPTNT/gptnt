from httpx import QueryParams
from pydantic import UUID4, BaseModel, ConfigDict, Field, field_validator

from gptnt.ktane.state.module_registry import module_registry
from gptnt.ktane.state.modules import KtaneModuleId


def compute_mission_key(components: list[KtaneModuleId], *, seed: int, rule_seed: int) -> str:
    """Stable, human-readable identity for a mission and its generated rules.

    The component order does not affect identity. The two seeds remain visible so records using the
    same bomb layout but different generated rules do not share a key.
    """
    sorted_modules = ",".join(sorted(str(component) for component in components))
    return f"{seed}|{rule_seed}|{sorted_modules}"


class KtaneMissionSpec(BaseModel):
    """Configuration for a mission in KTANE."""

    model_config = ConfigDict(
        validate_by_name=True, validate_by_alias=True, serialize_by_alias=True, frozen=True
    )

    seed: int = Field(ge=0, description="Random seed for mission generation")
    rule_seed: int = Field(
        default=1,
        ge=1,
        validation_alias="ruleSeed",
        serialization_alias="ruleSeed",
        description="Random seed for manual rule generation",
    )
    time_limit: int = Field(
        gt=0,
        validation_alias="timeLimit",
        serialization_alias="timeLimit",
        description="Time limit in seconds",
    )
    num_strikes_allowed: int = Field(
        default=3,
        ge=1,
        le=5,
        validation_alias="numStrikes",
        serialization_alias="numStrikes",
        description="Allowed mistakes before failure",
    )
    components: list[KtaneModuleId] = Field(
        description="List of required components in the mission"
    )
    optional_widgets: int = Field(
        ge=0,
        le=10,
        validation_alias="optWidgets",
        serialization_alias="optWidgets",
        description="Number of optional widgets",
    )

    needy_time: int = Field(
        default=60,
        gt=0,
        validation_alias="needyTime",
        serialization_alias="needyTime",
        description="Time before needy modules activate",
    )
    force_modules_to_front: bool = Field(
        default=False,
        validation_alias="isFront",
        serialization_alias="isFront",
        description="Whether bomb is front-facing",
    )
    time_scale: float = Field(
        default=1.0,
        ge=0.1,
        le=10.0,  # noqa: WPS432
        validation_alias="timeScale",
        serialization_alias="timeScale",
        description="Time scale multiplier",
    )
    time_step_size: int = Field(
        default=3000,  # noqa: WPS432
        validation_alias="timeStepSize",
        serialization_alias="timeStepSize",
        description="Used to detremine how long the time should advance for when using the command for it.",
    )

    @property
    def mission_key(self) -> str:
        """Stable identity for this mission's modules and both seeds."""
        return compute_mission_key(self.components, seed=self.seed, rule_seed=self.rule_seed)

    @property
    def requires_multiple_images_per_observation(self) -> bool:
        """Check if the mission requires multiple images per observation."""
        return any(
            module_registry().needs_multiple_frames(component) for component in self.components
        )

    @field_validator("components", mode="before")
    @classmethod
    def coerce_components(
        cls,
        components: str | list[KtaneModuleId],  # noqa: WPS110
    ) -> list[KtaneModuleId]:
        """Coerce a known component per identifier, keeping the raw id for a community module."""
        if isinstance(components, str):
            components = components.split(",") if "," in components else [components]
            components = [comp.strip() for comp in components]

        return components

    def to_query_params(self) -> QueryParams:
        """Converts the mission spec into a query parameter string for API requests."""
        specification_dict = self.model_dump(by_alias=True)
        specification_dict["components"] = (",".join(specification_dict["components"]),)
        return QueryParams(specification_dict)


class KtaneMissionConfig(KtaneMissionSpec):
    """Configuration for the game, which is just the mission spec plus the session ID."""

    session_id: UUID4 | None = Field(
        validation_alias="sessionId",
        serialization_alias="sessionId",
        description="UUID of the experiment session",
    )
