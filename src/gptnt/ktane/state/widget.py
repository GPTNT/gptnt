from typing import Literal, Union

from pydantic import BaseModel, ConfigDict, alias_generators

type KtaneWidget = Literal["Battery", "Indicator", "Port", "SerialNumber"]


class BaseWidgetState(BaseModel):
    """Base class for all widget states."""

    model_config = ConfigDict(
        alias_generator=alias_generators.to_camel, populate_by_name=True, extra="ignore"
    )
    name: KtaneWidget
    position: str


type _KnownBatteryTypes = Literal["D", "AA"]


class BatteryWidgetState(BaseWidgetState):
    """State of the Battery widget."""

    batteries_count: int
    battery_type: _KnownBatteryTypes | str


class IndicatorWidgetState(BaseWidgetState):
    """State of the Indicator widget."""

    light_activated: bool
    label: str


type _KnownPorts = Literal["DVI-D", "Parallel", "PS/2", "RJ-45", "Serial", "Stereo RCA"]


class PortWidgetState(BaseWidgetState):
    """State of the Port widget."""

    port_type: list[_KnownPorts | str]


class SerialWidgetState(BaseWidgetState):
    """State of the Serial Number widget."""

    serial_number: str


type WidgetStates = Union[  # noqa: UP007
    BatteryWidgetState, IndicatorWidgetState, PortWidgetState, SerialWidgetState
]
"""Widget states for the KTANE game."""
