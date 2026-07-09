from __future__ import annotations

from typing import TYPE_CHECKING

from hydra.utils import instantiate
from pydantic_ai import BinaryContent
from pydantic_ai.settings import merge_model_settings
from rich.console import Console
from rich.table import Table

from gptnt.common.hydra import compose_player_config
from gptnt.common.paths import Paths
from gptnt.processors.image_resizer import ImageResizer
from gptnt.prompts.manual import load_manual_image

if TYPE_CHECKING:
    from pathlib import Path

    from pydantic_ai import Agent

    from gptnt.players.specification import PlayerCapabilities

console = Console()

_PROMPT = "Reply with the single word: OK."
"""Identical text for both measurement requests, so the input-token delta is only the image."""

_CALIBRATION_MAX_TOKENS = 16
"""Cap output on both requests.

Output tokens don't affect the input count we read, but a low cap keeps each call fast and cheap.
"""

_MANUAL_FIRST_PAGE = 1


async def measure_tokens_per_image(player: str) -> None:
    """Measure player's per-image token cost from the model and update config.

    We do this so that we do not need to guess how much each image is worth in tokens, which is
    important for truncation and context accounting.

    Composes the player config, resizes the first manual page exactly as the player sees it,
    measures the per-image input-token cost, writes it into `configs/player/<player>.yaml`, and
    prints the result. SPENDS MONEY.
    """
    cfg = compose_player_config(player, None)
    capabilities: PlayerCapabilities = instantiate(cfg.player.capabilities)
    agent: Agent = instantiate(cfg.player.action_predictor.agent)

    image_bytes = _load_first_manual_page(capabilities)
    baseline, with_image = await _measure(agent, image_bytes)
    tokens_per_image = with_image - baseline

    if tokens_per_image <= 0:
        raise RuntimeError(
            f"Measured a non-positive per-image cost (baseline={baseline}, with_image={with_image}). "
            f"The provider may not report image tokens in the input-token count."
        )

    path = _write_tokens_per_image(player, tokens_per_image)
    _render(player, capabilities, baseline, with_image, tokens_per_image, path)


def _load_first_manual_page(capabilities: PlayerCapabilities) -> bytes:
    """The first manual page, resized to what the model reads (portrait: short x long side).

    This is the transform `load_manual_as_prompt` applies to every manual page. `image_dimensions`
    defaults to the KTANE settings unless the player config overrides it.
    """
    resizer = ImageResizer(
        target_width=capabilities.image_dimensions.short_side,
        target_height=capabilities.image_dimensions.long_side,
    )
    return load_manual_image(_MANUAL_FIRST_PAGE, image_kind="small", image_resizer=resizer)


async def _measure(agent: Agent, image_bytes: bytes) -> tuple[int, int]:
    """Return `(baseline_input_tokens, with_image_input_tokens)` for the same prompt.

    Starts from the agent's own `model_settings` and overrides only `max_tokens`, so the config's
    provider-correct thinking setting is preserved rather than clobbered. A per-request settings
    callable has no static value to start from, so we fall back to overriding just `max_tokens`.
    """
    base = None if callable(agent.model_settings) else agent.model_settings
    settings = merge_model_settings(base, {"max_tokens": _CALIBRATION_MAX_TOKENS})
    baseline = (await agent.run(_PROMPT, model_settings=settings)).usage.input_tokens
    with_image = (
        await agent.run(
            [_PROMPT, BinaryContent(image_bytes, media_type="image/png")], model_settings=settings
        )
    ).usage.input_tokens
    return baseline, with_image


def _write_tokens_per_image(player: str, tokens_per_image: int) -> Path:
    """Write `tokens_per_image` into `configs/player/<player>.yaml` and return its path."""
    path = Paths().player_configs / f"{player}.yaml"
    _ = path.write_text(_insert_tokens_per_image(path.read_text(), tokens_per_image))
    return path


def _insert_tokens_per_image(text: str, tokens_per_image: int) -> str:
    """Set `tokens_per_image` inside the `capabilities:` block of a player-config yaml.

    A surgical text edit: replace the existing `tokens_per_image:` line if present, else insert one
    directly under the `capabilities:` header. Everything else is left byte-for-byte, so comments
    and `${oc.env:...}` interpolations survive.
    """
    lines = text.splitlines(keepends=True)
    header = next(
        (index for index, line in enumerate(lines) if line.startswith("capabilities:")), None
    )
    if header is None:
        raise RuntimeError(
            "config has no top-level `capabilities:` block to write `tokens_per_image` into."
        )

    new_line = f"  tokens_per_image: {tokens_per_image}\n"
    for index in range(header + 1, _block_end(lines, header)):
        if lines[index].lstrip().startswith("tokens_per_image:"):
            lines[index] = new_line
            break
    else:
        lines.insert(header + 1, new_line)

    return "".join(lines)


def _block_end(lines: list[str], header: int) -> int:
    """Index of the first line after `header` that starts a new column-0 key (else end of file).

    Indented lines, blanks, and column-0 comments stay inside the block.
    """
    for offset, line in enumerate(lines[header + 1 :], start=header + 1):
        is_indented = line[:1] in {" ", "\t", "\n", ""}
        if not is_indented and not line.lstrip().startswith("#"):
            return offset
    return len(lines)


def _render(
    player: str,
    capabilities: PlayerCapabilities,
    baseline: int,
    with_image: int,
    tokens_per_image: int,
    path: Path,
) -> None:
    """Print the measurement and where it was written."""
    table = Table(title=f"Image-token calibration: {player}", show_header=False)
    table.add_row(
        "image", f"{capabilities.image_dimensions.width}x{capabilities.image_dimensions.height}"
    )
    table.add_row("baseline tokens", str(baseline))
    table.add_row("with one image", str(with_image))
    table.add_row("tokens per image", str(tokens_per_image))
    console.print(table)
    console.print(f"Wrote [bold]tokens_per_image={tokens_per_image}[/bold] to {path}")
