from typing import Annotated

import annotated_types
from pydantic import BaseModel

from gptnt.ktane.state import constants


class BatteryWidgetState(BaseModel):
    """State of the Battery widget."""

    position: constants.WidgetPosition
    batteries_count: int
    battery_type: constants.BatteryType


class IndicatorWidgetState(BaseModel):
    """State of the Indicator widget."""

    position: constants.WidgetPosition
    light_activated: bool
    label: Annotated[str, annotated_types.MaxLen(3), annotated_types.MinLen(3)]


class PortWidgetState(BaseModel):
    """State of the Port widget."""

    position: constants.WidgetPosition
    port_type: constants.PortType


type WidgetStates = BatteryWidgetState | IndicatorWidgetState | PortWidgetState
