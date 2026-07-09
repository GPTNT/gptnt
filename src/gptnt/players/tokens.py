from functools import lru_cache

import tiktoken
from tiktoken.model import MODEL_PREFIX_TO_ENCODING

TIKTOKEN_ENCODING_NAME = MODEL_PREFIX_TO_ENCODING["gpt-5-"]


@lru_cache
def count_tokens_from_text(string: str) -> int:
    """Count the number of tokens in a string."""
    encoding = tiktoken.get_encoding(TIKTOKEN_ENCODING_NAME)
    num_tokens = len(encoding.encode(string))
    return num_tokens
