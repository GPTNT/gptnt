from functools import lru_cache

from gptnt.common.paths import Paths

paths = Paths()

reflection_prompt_path = paths.storage.joinpath("reflection_prompt")


@lru_cache(maxsize=1)
def load_reflection_prompt() -> str:
    """Load the prompt for the given state."""
    return reflection_prompt_path.joinpath("reflection_prompt.txt").read_text()
