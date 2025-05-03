import math

import tiktoken
from tiktoken.model import MODEL_PREFIX_TO_ENCODING

TIKTOKEN_ENCODING_NAME = MODEL_PREFIX_TO_ENCODING["gpt-4o-"]

DEFAULT_IMAGE_WIDTH = 512
DEFAULT_IMAGE_HEIGHT = 384


def estimate_tokens_for_image_per_model(model: str, *, width: int, height: int) -> int:  # noqa: WPS212
    """Get the computation function for the model."""
    if "claude" in model:
        return math.ceil(width * height / 750)
    if "gemini" in model:
        return 1290
    if "gpt4o" in model or "gpt-4o" in model:
        return 85
    if "Qwen" in model:
        # resized to 504x504 (multiples of 28)
        # patch size is 14x14 - 2x2 token merging
        # (504 / 14)^2 / 2^2 = 324
        return 324
    if "llama" in model:
        # return math.ceil(width * height / LLAMA_32_VISION_PATCH_SIZE / LLAMA_32_VISION_PATCH_SIZE)
        raise NotImplementedError
    if "InternVL3" in model:
        # resized to 448x448 (multiples of 448)
        # patch size is 14x14 - pixel unshuffle == 2x2 token reduction
        # (448 / 14)^2 / 2^2 = 256
        return 256
    if (model == "test") or ("function:" in model):
        # Use a big number for the test models
        return 1290
    raise ValueError(f"Unknown model: {model}")


def count_tokens_from_text(string: str) -> int:
    """Count the number of tokens in a string."""
    encoding = tiktoken.get_encoding(TIKTOKEN_ENCODING_NAME)
    num_tokens = len(encoding.encode(string))
    return num_tokens
