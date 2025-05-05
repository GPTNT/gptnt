from functools import lru_cache
from typing import Literal

import logfire
import structlog
from pydantic_ai import BinaryContent

from gptnt.common.paths import Paths
from gptnt.dialogue_space.client import DialogueSpaceClient
from gptnt.ktane.client import KtaneClient
from gptnt.ktane.manual import MANUAL_NUM_PAGES, KtaneManualPaths

log = structlog.get_logger()

paths = Paths()

logger = structlog.get_logger()


@lru_cache(maxsize=1)
def load_reflection_prompt() -> str:
    """Load the prompt for the given state."""
    return paths.storage.joinpath("reflection_prompt", "reflection_prompt.txt").read_text()


BombStateMessage = Literal["terminated-exploded", "truncated-exploded", "terminated-defused"]


@logfire.instrument("Send reflection message to agents")
async def send_reflection_message(*, ktane_url: str, dialogue_space_url: str) -> None:
    """Send the reflection message to the agent from the bomb state."""
    async with KtaneClient(url=ktane_url) as ktane_client:
        last_bomb_state = await ktane_client.get_state()

    if last_bomb_state is None:
        logger.exception("No bomb state found")
        return

    final_message: BombStateMessage | None = None
    if last_bomb_state.is_detonated is True:
        if last_bomb_state.timer_module.seconds_remaining <= 0:
            # bomb detonated because player ran out of time
            final_message = "terminated-exploded"
        else:
            # bomb detonated because player made too many mistakes
            final_message = "truncated-exploded"

    if last_bomb_state.is_solved is True:
        # player solved all modules on bomb
        final_message = "terminated-defused"

    if not final_message:
        logger.exception("No logic connecting bomb state to final message")
        return

    ds_client = DialogueSpaceClient.from_url(dialogue_space_url)
    await ds_client.connect(is_player=False)
    _ = await ds_client.send_message(final_message)
    await ds_client.disconnect()


NEEDY_MODULE_PAGE_NUMS = tuple(range(17, 21))


@lru_cache(maxsize=1)
def load_manual_as_prompt(
    *, num_pages: int = MANUAL_NUM_PAGES, skip_needy_modules: bool = True
) -> list[str | BinaryContent]:
    """Load the content for the manual."""
    log.debug(f"Loading {num_pages} pages of the manual")
    manual_paths = KtaneManualPaths()

    manual = []
    for page_num in range(1, num_pages + 1):
        if skip_needy_modules and page_num in NEEDY_MODULE_PAGE_NUMS:
            # Skip the needy module pages
            continue

        # Load the text for the page first
        text = manual_paths.load_text(page_num)
        manual.append(text)

        # Load the image for the page afterwards
        image = manual_paths.load_image(page_num, kind="512")
        image = BinaryContent(image, media_type="image/png")
        manual.append(image)

    return manual
