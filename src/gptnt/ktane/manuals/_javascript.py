"""Load JavaScript expressions executed by the manual browser."""

from functools import cache
from importlib.resources import files


@cache
def load_javascript(name: str) -> str:
    """Read and cache one packaged browser expression by filename."""
    # importlib.resources works for both editable source trees and installed wheels.
    return files("gptnt.ktane.manuals").joinpath("_js", name).read_text(encoding="utf-8")
