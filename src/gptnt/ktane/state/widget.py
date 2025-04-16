from typing import Annotated

import annotated_types
from pydantic import BaseModel, ConfigDict, alias_generators

from gptnt.ktane.state import constants


class BaseWidgetState(BaseModel):
    """Base class for all widget states."""

    model_config = ConfigDict(alias_generator=alias_generators.to_snake, populate_by_name=True)
    position: constants.WidgetPosition


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

    port_type: list[constants.PortType] | None


class SerialWidgetState(BaseWidgetState):
    """State of the Serial Number widget."""

    serial_number: str


type WidgetStates = BatteryWidgetState | IndicatorWidgetState | PortWidgetState | SerialWidgetState
