"""Load JavaScript expressions executed by the manual browser."""

from functools import cache
from importlib.resources import files


@cache
def load_javascript(name: str) -> str:
    """Read one packaged browser expression by filename."""
    return files("gptnt.ktane.manuals").joinpath("_js", name).read_text(encoding="utf-8")
