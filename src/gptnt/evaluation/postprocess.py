from collections.abc import Callable

type PostProcessModelOutputsFunc = Callable[[str], str]


def noop(output: str) -> str:
    """No-op postprocessing function."""
    return output


def default(output: str) -> str:
    """Default postprocessing function that strips whitespace."""
    return output.lower().strip()


def expert_ocr_postprocess(output: str) -> str:
    """Postprocessing function for expert OCR outputs."""
    raise NotImplementedError("Expert OCR postprocessing is not implemented yet.")
