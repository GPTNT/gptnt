import pytest

from gptnt.statics.output import extract_static_answer, static_prediction_answer


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        ("B", "B"),
        ("<B>", "B"),
        ("<thought>Compare the options.</thought>B", "B"),
        ("<thought>Legacy output.</thought><action>B</action>", "B"),
        ("<thought>Legacy malformed tag.</thought><action>B", "B"),
        ("Reasoning.\nFinal answer: C", "C"),
        ('<thought>Locate it.</thought>{"x": 468, "y": 535}', '{"x": 468, "y": 535}'),
        (
            "<thinking>Return the coordinates inside an `<action>` block as requested."
            '</thinking>\n\n<action>{"x": 433, "y": 243}</action>',
            '{"x": 433, "y": 243}',
        ),
    ],
)
def test_extract_static_answer(response: str, expected: str) -> None:
    assert extract_static_answer(response) == expected


def test_prediction_falls_back_to_raw_output_after_legacy_parser_failure() -> None:
    prediction = {"output": "", "raw_output": "<thought>The second option matches.</thought><B>"}

    assert static_prediction_answer(prediction) == "B"
