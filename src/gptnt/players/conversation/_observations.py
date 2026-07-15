import copy

from pydantic_ai import BinaryContent
from pydantic_ai.messages import ModelMessage, ModelRequest, UserPromptPart

from gptnt.players.conversation._entry import Entry


def remove_binary_content_from_model_request(
    message: ModelRequest, *, keep_last: bool
) -> tuple[int, ModelRequest]:
    """Remove binary content from a model request.

    Args:
        message: The model request to clean
        keep_last: If True, keeps the last BinaryContent in each part

    Returns:
        Tuple of (number removed, cleaned message)
    """
    num_removed = 0
    clean_message = copy.deepcopy(message)

    for part in clean_message.parts:
        if not isinstance(part, UserPromptPart) or isinstance(part.content, str):
            continue

        content_list = list(part.content)

        num_observations = sum(1 for piece in content_list if isinstance(piece, BinaryContent))
        # For the remaining parts, remove all binary content except optionally the last one
        binary_indices = [
            idx for idx, piece in enumerate(content_list) if isinstance(piece, BinaryContent)
        ]
        # Determine which indices to keep
        keep_indices = set(binary_indices[-1:]) if keep_last else set()

        # Remove any indices that are not in keep_indices
        remaining_parts = [
            piece
            for idx, piece in enumerate(content_list)
            if idx in keep_indices or not isinstance(piece, BinaryContent)
        ]
        num_removed += num_observations - len(keep_indices)
        part.content = remaining_parts
    return num_removed, clean_message


def remove_binary_content_from_messages(
    messages: list[ModelMessage], *, keep_last: bool
) -> list[ModelMessage]:
    """Copy of `messages` with binary content removed, optionally keeping the last per part."""
    return [
        remove_binary_content_from_model_request(message, keep_last=keep_last)[1]
        if isinstance(message, ModelRequest)
        else message
        for message in messages
    ]


def remove_binary_content_outside_window(*, entries: list[Entry], window: int) -> list[Entry]:
    """Return a view with binary content removed from non-pinned entries outside the window.

    Within-window non-pinned entries keep the last binary content per part. Earlier non-pinned
    entries keep none. Pinned entries pass through unchanged.
    """
    non_pinned = [index for index, entry in enumerate(entries) if not entry.pinned]
    window_start = max(len(non_pinned) - window, 0)
    keep_last_indices = set(non_pinned[window_start:]) if window > 0 else set()

    view: list[Entry] = []
    for index, entry in enumerate(entries):
        if entry.pinned:
            view.append(entry)
        else:
            keep_last = index in keep_last_indices
            view.append(
                Entry(
                    messages=remove_binary_content_from_messages(
                        entry.messages, keep_last=keep_last
                    )
                )
            )
    return view
