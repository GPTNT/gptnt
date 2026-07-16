"""Stateless token-size estimate for a rendered prompt, used to decide truncation.

The only question truncation answers is whether the history plus the next observation fits under
`input_tokens_limit`. Images carry the weight of a vision prompt, so each counts as the calibrated
`tokens_per_image`. Text is the small, low-variance part, so it is estimated from its length at a
fixed characters-per-token ratio rather than a real tokenizer — good enough to size it, with no
extra dependency.
"""

import math

from pydantic_ai import BinaryContent

from gptnt.players.conversation._entry import Entry

_CHARS_PER_TOKEN = 4
"""Rough characters-per-token ratio for text (English averages about four)."""


def _scan_messages(entry: Entry) -> tuple[int, int, int]:
    """Return `(text_chars, image_bearing_parts, total_images)` across an entry's messages.

    `image_bearing_parts` is how many images survive the observation window, which keeps the last
    image per part; `total_images` is every image, which is what pinned entries keep.
    """
    text_chars = 0
    image_bearing_parts = 0
    total_images = 0
    for message in entry.messages:
        for part in message.parts:
            content = getattr(part, "content", None)
            if isinstance(content, str):
                text_chars += len(content)
                continue
            if isinstance(content, list | tuple):
                part_images = sum(isinstance(piece, BinaryContent) for piece in content)
                total_images += part_images
                image_bearing_parts += part_images > 0
                text_chars += sum(len(_piece_text(piece)) for piece in content)
                continue
            text_chars += len(_piece_text(part))
    return text_chars, image_bearing_parts, total_images


def _piece_text(piece: object) -> str:
    """Best-effort text of a message piece, empty for anything without string content."""
    if isinstance(piece, str):
        return piece
    inner = getattr(piece, "content", None)
    if isinstance(inner, str):
        return inner
    args = getattr(piece, "args", None)
    return str(args) if args is not None else ""


def estimate_rendered_tokens(entry: Entry, *, in_window: bool, tokens_per_image: int) -> int:
    """Estimate the tokens `entry` contributes to a render, sized as it will be sent.

    Pinned entries keep every image. Non-pinned entries in the observation window keep the last
    image per part; older ones have their images stripped and are sized by their text alone.
    """
    text_chars, image_bearing_parts, total_images = _scan_messages(entry)
    text_tokens = math.ceil(text_chars / _CHARS_PER_TOKEN)
    if entry.pinned:
        images = total_images
    elif in_window:
        images = image_bearing_parts
    else:
        images = 0
    return text_tokens + images * tokens_per_image
