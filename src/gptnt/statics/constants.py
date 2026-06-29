"""Shared scoring constants for static evaluation.

Module names, grounding/keypad answer keys, and the task-type alias used by the evaluation scorers,
prompts, and CLI. Self-contained domain data (no generation deps).
"""

from types import MappingProxyType
from typing import Literal

from gptnt.ktane.state.modules import KtaneComponent

type TaskType = Literal["vqa", "oe", "grounding", "expert_vqa"]

GROUNDING_HALLUCINATION_TYPE_A_RESPONSE = "More information needed"
GROUNDING_HALLUCINATION_TYPE_B_RESPONSE = "None"

MODULE_NAMES = MappingProxyType(
    {
        KtaneComponent.wires: "Wires",
        KtaneComponent.big_button: "Button",
        KtaneComponent.keypad: "Keypad",
        KtaneComponent.simon: "Simon Says",
        KtaneComponent.whos_on_first: "Who's On First",
        KtaneComponent.memory: "Memory",
        KtaneComponent.morse_code: "Morse Code",
        KtaneComponent.venn: "Complicated Wires",
        KtaneComponent.wire_sequence: "Wire Sequence",
        KtaneComponent.maze: "Maze",
        KtaneComponent.password: "Password",
    }
)

KEYPAD_SYMBOL_DESCRIPTIONS: MappingProxyType[str, list[str]] = MappingProxyType(
    # First value is ground truth, following values are alternate names
    {
        "copyright": [
            "copyright",
            "Copyright sign",
            "copyright symbol",
            "c in a circle",
            "copyright c",
            "\u00a9",
        ],
        "star": ["filled star", "Black star", "dark star", "filled in star", "\u2605", "\u066d"],
        "hollow-star": ["hollow star", "White star", "outline star", "star", "\u2606"],
        "pashto-teh": [
            "smiley face",
            "Arabic letter Teh with ring",
            "smiley face with a tongue sticking out",
            "smiling face",
            "two eyes and a mouth with a circle below it",
            "Arabic letter T with a small circle at the bottom",
            "\u062a with a ring",
            "\u062a with a circle at the bottom",
            "\u067c",
            "ü",  # added from GPT5.2 predictions
            "☺",  # added from GPT5.2 chat predictions
            "\u263a",  # added from GPT5.2 chat predictions
            "ت",  # added from Gemini predictions
            "\u062a",  # added from Gemini predictions
            "magnet",  # added from GPT 5.2 chat and Claude predictions
            "smile",  # added from Gemini predictions
        ],
        "zh": [
            "double k",
            "Cyrillic capital leter Zhe with descender",
            "back to back Ks",
            "2 Ks back to back",
            "X with a vertical line in the middle",
            "two mirrored kappas",
            "an X with an I in the middle",
            "\u0416",
            "\u0436",
            "\u0496",
            "\u0497",
        ],
        "omega": [
            "omega",
            "Greek capital letter Omega",
            "ohm",
            "omega",
            "god of war logo",
            "octopus",
            "\u03a9",
        ],
        "ligature-iotated-e": [
            "squid knife",
            "Cyrillic capital letter iotified Big Yus",
            "spider charging",
            "Warrior with a staff",
            "squid holding on to a wall",
            "Rocket about to launch",
            "Tripod on a stand",
            "\u046c",
            "\u046d",
        ],
        "ot": [
            "pumpkin",
            "Cyrillic capital letter Omega with Titlo",
            "wobbly W with a comma at the top",
            "distorted W topped with a comma",
            "W with a comma at the top",
            "W with an apostrophe above",
            "an apostrophe above a W",
            "\u047c",
            "\u047d",
            "Moustache",  # added from GPT 5.2 predictions
            "ω",  # added from Gemini predictions
            "\u03c9",  # added from Gemini predictions
        ],
        "kai": [
            "hook n",
            "Coptic symbol Kai",
            "curly H",
            "Fancy H with a thing at the bottom",
            "cursive H monogram",
            "\u03cf",
            "\u03d7",
            "ϰ",
            "\u03ba",  # dded from Gemini predictions
            "א",  # added from Claude predictions
            "\u05d0",  # added from Claude predictions
        ],
        "lunate-sampi": [
            "six",
            "Cyrillic small letter Be",
            "6 with flattened top",
            "lowercase Greek letter delta",
            "2nd letter in the Russian alphabet",
            "The number 6flattened six",
            "\u0411",
            "\u0431",
        ],
        "qoppa": [
            "squiggly n",
            "Greek letter archaic Koppa",
            "backwards n",
            "squiggle from top left to bottom right",
            "\u03de",
            "\u03df",
        ],
        "little-yus": [
            "AT",
            "Cyrillic capital letter Little Yus",
            "miniature T inside of an A",
            "A with a third leg",
            "Tripod",
            "\u0467",
            "\u0466",
        ],
        "ha-with-descender": [
            "melted three",
            "Cyrillic capital letter Komi Dzje",
            "R with a stick and a thing at the bottom",
            "melting 3",
            "The top half of a three with a tail",
            "\u0506",
            "\u0507",
            "R",  # added from GPT 5.2 chat predictions
        ],
        "ae": [
            "ae",
            "Latin small letter AE",
            "ae squished together",
            "french ae",
            "Norweigan/Danish ae",
            "Latin diphthong ae",
            "\u00e6",
        ],
        "e-with-diaeresis": [
            "euro",
            "Cyrillic capital letter E with diaeresis",
            "backwards E with umlaut",
            "Backwards capital E with 2 dots at the top",
            "backwards epsilon with eyes",
            "backwards euro symbol",
            "two dots above a backwards euro symbol",
            "\u044d",
            "\u042d",
        ],
        "short-i": [
            "n with hat",
            "Cyrillic capital letter short I with tail",
            "upside down N with septum piercing above",
            "N with a squiggle at the top and a comma at the bottom",
            "Russian semi-vowel 'y'",
            "\u0439",
            "\u0419",
        ],
        "ksi": [
            "dragon",
            "Cyrillic capital letter Ksi",
            "3 with an extra curve at the bottom",
            "A three with antennae and a tail",
            "Alien three",
            "three with antlers and a tail",
            "\u046e",
            "\u046f",
            "3k",  # added from GPT 5.2 predictions
            "3",  # added from Gemini predictions
        ],
        "inverted-question": [
            "question mark",
            "inverted question mark",
            "upside down question mark",
            "Spanish opening question mark",
            "\u00bf",
        ],
        "pilcrow": [
            "paragraph",
            "pilcrow sign",
            "paragraph symbol",
            "backwards p that has been filled in",
            "\u00b6",
        ],
        "lunate-epsilon": [
            "right c",
            "Greek capital dotted lunate Sigma symbol",
            "C with a dot inside",
            "circle with a hole on the right side with a dot in the middle",
            "right ear",
            "\u037c",
            "\u03fe",
            "C with a dot",  # added from Gemini predictions
        ],
        "reversed-lunate-epsilon": [
            "left c",
            "Greek capital reversed dotted lunate Sigma symbol",
            "Backwards C with a dot inside",
            "circle with a hole on the left side with a dot in the middle",
            "left ear",
            "\u037d",
            "\u03ff",
        ],
        "psi": [
            "pitchfork",
            "Greek capital letter Psi",
            "trident",
            "poseidon",
            "candelabra",
            "an I with wings",
            "an I with horns",
            "\u03a8",
            "capital \u03c8",
        ],
        "qa": [
            "cursive",
            "Cyrillic capital letter Abkhasian Ha",
            "Fancy O",
            "A spring",
            "\u04a8",
            "\u04a9",
        ],
        "titlo": [
            "tracks",
            "Cyrillic thousands sign",
            "Puzzle piece",
            "Train tracks",
            "dumbbell weight",
            "not equal sign",
            "\u0482",
        ],
        "archaic-koppa": [
            "balloon",
            "Greek small letter Koppa",
            "circle with a line below",
            "O but with a vertical line at the bottom",
            "Mirror",
            "\u03d8",
            "\u03d9",
            "circle with a vertical line",  # added from GPT 5.2 (chat) predictions
            "O with a vertical line",  # added from Gemini predictions
        ],
        "lambda-bar": [
            "upside down y",
            "Latin small letter lambda with stroke",
            "lambda with a line through it",
            "lambda with a dash",
            "The lambda symbol with a line through the top of it",
            "A tent",
            "\u019b",
            "\u03bb with stroke",
            "λ̅",  # added from Gemini predictions
            "\u03bb\u0305",  # added from Gemini predictions
            "lambda with a bar",  # added from Gemini predictions
            "λ",  # added from all models' predictions
            "\u03bb",  # added from all models' predictions
            "入",  # added from Claude predictions
            "\u5165",  # added from Claude predictions
        ],
        "yat": [
            "bT",
            "Cyrillic capital letter Yat",
            "b and T combined",
            "B/T logo",
            "A B and a T merged together",
            "\u0462",
            "\u0463",
            "Б",  # from GPT 5.2 (chat) and Claude predictions
            "\u0411",  # from GPT 5.2 (chat) and Claude predictions
            "ƀ",  # from GPT 5.2 predictions
            "\u0180",  # from GPT 5.2 predictions
            "Ъ",  # from Claude predictions
            "\u042a",  # from Claude predictions
            "tb",  # from InternVL predictions
            "b",  # from all models' predictions
        ],
    }
)

EXCLUDED_MODULES = frozenset(
    (
        KtaneComponent.timer,
        KtaneComponent.empty,
        KtaneComponent.needy_capacitor,
        KtaneComponent.needy_vent_gas,
        KtaneComponent.needy_knob,
    )
)


def get_valid_modules() -> list[KtaneComponent]:
    """Get list of valid modules (excluding timer, empty, and needy modules)."""
    return [module for module in KtaneComponent if module not in EXCLUDED_MODULES]
