import re
from collections.abc import Callable

type PostProcessModelOutputsFunc = Callable[[str], str]


def noop(output: str) -> str:
    """No-op postprocessing function."""
    return output


def default(output: str) -> str:
    """Default postprocessing function that strips whitespace."""
    return output.lower().replace("```json", "").replace("```", "").strip()


def expert_ocr_postprocess(output: str) -> str:
    """Postprocessing function for expert OCR outputs."""
    output = default(output)
    output = re.sub(r"\s+", " ", output)
    allowed_chars = r"(what\s*\?|\d\.\d{3}|★|\*|[a-z0-9]|\s)"
    adjacent_asterisks = r"(?<=\S)\*|\*(?=\S)"
    # Keeps only alphanumeric characters and the following special patterns:
    # ? preceded by "what" (for Who's on First)
    # digit . 3 digits (for morse code)
    # ★ or a * on its own (for complicated wires)
    output = "".join(match.group(0) for match in re.finditer(allowed_chars, output))
    return re.sub(adjacent_asterisks, "", output)
