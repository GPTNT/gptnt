import json
import re
from collections.abc import Callable

import json_repair
from pydantic_core import from_json

type PostProcessModelOutputsFunc = Callable[[str], str]


def noop(output: str) -> str:
    """No-op postprocessing function."""
    return output


def default_postprocess(output: str) -> str:
    """Default postprocessing function that strips whitespace."""
    return output.lower().replace("```json", "").replace("```", "").strip()


def expert_ocr_postprocess(output: str) -> str:
    """Postprocessing function for expert OCR outputs."""
    output = default_postprocess(output)
    output = re.sub(r"<br\s*/?>", " ", output)  # strip <br>
    output = re.sub(r"\s+", " ", output)
    allowed_chars = r"(what\s*\?|\d\.\d{3}|★|[a-z0-9]|\s)"
    # Keeps only alphanumeric characters and the following special patterns:
    # ? preceded by "what" (for Who's on First)
    # digit . 3 digits (for morse code)
    # ★ (for complicated wires)
    # Strips: newlines, hyphens, bullets, commas, double quotes, <br> tags
    return "".join(match.group(0) for match in re.finditer(allowed_chars, output))


def convert_normalised_to_absolute(
    model_output: str, *, image_width: int, image_height: int, normalised_upper_bound: int = 1000
) -> str:
    """Convert normalised coordinate output to absolute coordinate."""
    model_output = default_postprocess(model_output)
    try:
        normalised_coord = from_json(json_repair.repair_json(model_output))
    except ValueError:
        return model_output

    absolute_x = int(normalised_coord["x"] * image_width / normalised_upper_bound)
    absolute_y = int(normalised_coord["y"] * image_height / normalised_upper_bound)
    return json.dumps({"x": absolute_x, "y": absolute_y})
