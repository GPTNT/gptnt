from typing import Literal

type KeypadSymbol = Literal[
    "copyright",
    "star",
    "hollow-star",
    "pashto-teh",
    "zh",
    "omega",
    "ligature-iotated-e",
    "ot",
    "kai",
    "egyptian-kai",
    "lunate-sampi",
    "qoppa",
    "little-yus",
    "ae",
    "ha-with-descender",
    "e-with-diaeresis",
    "thousand-sign",
    "short-i",
    "ksi",
    "inverted-question",
    "pilcrow",
    "lunate-epsilon",
    "reversed-lunate-epsilon",
    "psi",
    "big-yus",
    "qa",
    "titlo",
    "archaic-koppa",
    "zeta",
    "lambda-bar",
    "yat",
]

type SimonSaysColor = Literal["red", "blue", "green", "yellow"]

type ComplicatedWireColor = Literal["white", "red", "blue", "white_red", "white_blue", "red_blue"]

type KnobPosition = Literal["up", "down", "left", "right"]

type MorseCodes = Literal["dot", "dash", "blank"]

type GasMessages = Literal["Vent", "Detonate"]

type WireSequenceColor = Literal["red", "blue", "black"]

type WireSetColor = Literal["red", "yellow", "blue", "black", "white"]

type ButtonColor = Literal["red", "blue", "yellow", "black", "white"]

type WidgetPosition = Literal["top", "bottom", "left", "right"]

type BatteryType = Literal["D", "AA"]

type PortType = Literal["DVI-D", "Parallel", "PS/2", "RJ-45", "Serial", "Stereo RCA"]

type ButtonWord = Literal["Abort", "Detonate", "Hold", "Press"]

type ButtonStripColor = Literal["red", "blue", "yellow", "white"]

type KeyPadButtonColor = Literal["green", "red"]
