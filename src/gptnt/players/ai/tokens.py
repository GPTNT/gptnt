from functools import lru_cache

import tiktoken
from tiktoken.model import MODEL_PREFIX_TO_ENCODING

TIKTOKEN_ENCODING_NAME = MODEL_PREFIX_TO_ENCODING["gpt-5-"]


def estimate_tokens_for_image_per_model(model: str, *, long_side: int, short_side: int) -> int:  # noqa: WPS212, WPS218
    """Get the computation function for the model.

    This needs to be improved to support more models and be more accurate.
    """
    model = model.lower()
    if "claude46" in model:
        assert long_side == 640
        assert short_side == 480
        return 424
    if "gemini-3" in model:
        assert long_side == 640
        assert short_side == 480
        return 541
    if "gpt5" in model or "gpt-5" in model:
        assert long_side == 640
        assert short_side == 480
        return 383
    if "qwen3vl" in model or "qwen35" in model:
        assert long_side == 504
        assert short_side == 504
        return 266
    if "internvl35" in model:
        assert long_side == 448
        assert short_side == 448
        return 267
    if "test" in model or ("function:" in model):
        return 258
    raise ValueError(f"Unknown model: {model}")


@lru_cache
def count_tokens_from_text(string: str) -> int:
    """Count the number of tokens in a string."""
    encoding = tiktoken.get_encoding(TIKTOKEN_ENCODING_NAME)
    num_tokens = len(encoding.encode(string))
    return num_tokens
