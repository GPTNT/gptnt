from enum import Enum
from typing import Annotated, Union

import annotated_types
from pydantic import BaseModel, ConfigDict, alias_generators

from gptnt.core.ktane.state import constants


class KtaneWidget(Enum):
    """Enum representing valid KTANE widgets."""

    battery = "Battery"
    indicator = "Indicator"
    port = "Port"
    serial_number = "SerialNumber"


class BaseWidgetState(BaseModel):
    """Base class for all widget states."""

    model_config = ConfigDict(
        alias_generator=alias_generators.to_camel, populate_by_name=True, extra="ignore"
    )
    position: constants.WidgetPosition
    name: KtaneWidget


class BatteryWidgetState(BaseWidgetState):
    """State of the Battery widget."""

    batteries_count: int
    battery_type: constants.BatteryType


class IndicatorWidgetState(BaseWidgetState):
    """State of the Indicator widget."""

    light_activated: bool
    label: Annotated[str, annotated_types.MaxLen(3), annotated_types.MinLen(3)]


class PortWidgetState(BaseWidgetState):
    """State of the Port widget."""

    port_type: list[constants.PortType]


class SerialWidgetState(BaseWidgetState):
    """State of the Serial Number widget."""

    serial_number: str


type WidgetStates = Union[  # noqa: UP007
    BatteryWidgetState, IndicatorWidgetState, PortWidgetState, SerialWidgetState
]
"""Widget states for the KTANE game."""
