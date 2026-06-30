import hashlib
import json
from typing import Any

from pydantic_core import to_jsonable_python


def stable_digest(payload: Any) -> str:
    """Short, order-stable hex digest of a JSON-able payload.

    Deterministic across processes and machines, unlike the built-in `hash()` (which randomises
    string hashing per process), so it can be written into records and compared between runs. Keys
    are sorted before hashing, then blake2b'd to a 16-byte hex digest.
    """
    return hashlib.blake2b(
        json.dumps(to_jsonable_python(payload), sort_keys=True).encode(), digest_size=16
    ).hexdigest()
