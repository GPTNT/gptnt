from typing import Literal

type KeypadSymbol = Literal[
    "doublek",
    "omega",
    "squidknife",
    "pumpkin",
    "hookn",
    "teepee",
    "six",
    "squigglyn",
    "at",
    "ae",
    "meltedthree",
    "euro",
    "nwithhat",
    "dragon",
    "questionmark",
    "paragraph",
    "pitchfork",
    "cursive",
    "tracks",
    "balloon",
    "upsidedowny",
    "bt",
]

type SimonSaysColor = Literal["red", "blue", "green", "yellow"]

type ComplicatedWireColor = Literal["white", "red", "blue", "White_red", "white_blue", "red_blue"]

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

type ButtonStripColour = Literal["red", "blue", "yellow", "white"]

type KeyPadButtonColour = Literal["Green", "Red"]
