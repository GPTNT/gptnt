import copy
from collections.abc import Iterator

from pydantic_ai import BinaryContent
from pydantic_ai.messages import ModelMessage, ModelRequest, UserPromptPart

from gptnt.players.conversation._entry import Entry


def partition_non_pinned_by_window(
    entries: list[Entry], *, window: int
) -> tuple[list[int], set[int]]:
    """Split non-pinned entry indices by the last `window` turns: (aged, in_window).

    `aged` are the non-pinned entries that fall outside the window; `in_window` are the rest. A
    non-positive window ages every non-pinned entry.
    """
    non_pinned = [index for index, entry in enumerate(entries) if not entry.pinned]
    split = max(len(non_pinned) - window, 0) if window > 0 else len(non_pinned)
    return non_pinned[:split], set(non_pinned[split:])


def remove_binary_content_from_model_request(
    message: ModelRequest, *, keep_last: bool
) -> ModelRequest:
    """Copy of `message` with binary content stripped from its user-prompt parts.

    Keeps the last BinaryContent per part when `keep_last`. Returns the message unchanged, without
    copying, when it holds no strippable binary content.
    """
    has_binary = any(
        isinstance(part, UserPromptPart)
        and not isinstance(part.content, str)
        and any(isinstance(piece, BinaryContent) for piece in part.content)
        for part in message.parts
    )
    if not has_binary:
        return message

    clean_message = copy.deepcopy(message)
    for part in clean_message.parts:
        if not isinstance(part, UserPromptPart) or isinstance(part.content, str):
            continue
        content_list = list(part.content)
        binary_indices = [
            idx for idx, piece in enumerate(content_list) if isinstance(piece, BinaryContent)
        ]
        keep_indices = set(binary_indices[-1:]) if keep_last else set()
        part.content = [
            piece
            for idx, piece in enumerate(content_list)
            if idx in keep_indices or not isinstance(piece, BinaryContent)
        ]
    return clean_message


def remove_binary_content_from_messages(
    messages: list[ModelMessage], *, keep_last: bool
) -> list[ModelMessage]:
    """Copy of `messages` with binary content removed, optionally keeping the last per part."""
    return [
        remove_binary_content_from_model_request(message, keep_last=keep_last)
        if isinstance(message, ModelRequest)
        else message
        for message in messages
    ]


def remove_binary_content_outside_window(*, entries: list[Entry], window: int) -> Iterator[Entry]:
    """Return a view with binary content removed from non-pinned entries outside the window.

    Within-window non-pinned entries keep the last binary content per part. Earlier non-pinned
    entries keep none. Pinned entries pass through unchanged.
    """
    _, in_window = partition_non_pinned_by_window(entries, window=window)

    for index, entry in enumerate(entries):
        if entry.pinned:
            yield entry
        else:
            yield Entry(
                messages=remove_binary_content_from_messages(
                    entry.messages, keep_last=index in in_window
                )
            )
