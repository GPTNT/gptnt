import io
from pathlib import Path
from typing import Annotated

from cyclopts import Parameter
from cyclopts.types import ExistingFile
from hydra.utils import instantiate
from pydantic_ai import Agent, BinaryContent
from pydantic_ai.settings import merge_model_settings
from rich.console import Console
from rich.table import Table

from gptnt.cli.params import PlayerOption, ProviderOption
from gptnt.common.hydra import compose_player_config
from gptnt.common.image_ops import load_observation_from_bytes
from gptnt.common.paths import Paths
from gptnt.players.specification import PlayerCapabilities
from gptnt.processors.image_resizer import ImageResizer

console = Console()

_PROMPT = "Reply with the single word: OK."
"""Identical text for both measurement requests, so the input-token delta is only the image."""

_CALIBRATION_MIN_MAX_TOKENS = 256
"""Minimum output allowance for both requests.

Reasoning models may spend dozens of tokens in their private reasoning channel before producing the
requested one-word response. Use at least this much room while preserving a larger player-
configured limit. Output tokens do not affect the input-token delta being measured.
"""


async def measure_tokens_per_image(
    player: PlayerOption,
    calibration_image: Annotated[
        ExistingFile,
        Parameter(help="Manual-page PNG used to measure the player's per-image token cost."),
    ],
    provider: ProviderOption = None,
) -> None:
    """Measure player's per-image token cost from the model and update config.

    We do this so that we do not need to guess how much each image is worth in tokens, which is
    important for truncation and context accounting.

    Composes the player config, resizes the supplied PNG to the portrait dimensions used for manual
    pages, measures the per-image input-token cost, writes it into `configs/player/<player>.yaml`,
    and prints the result. SPENDS MONEY.
    """
    cfg = compose_player_config(player, provider)
    capabilities: PlayerCapabilities = instantiate(cfg.player.capabilities)
    agent: Agent = instantiate(cfg.player.action_predictor.agent)

    image_bytes = _load_calibration_image(calibration_image, capabilities=capabilities)
    baseline, with_image = await _measure(agent, image_bytes)
    tokens_per_image = with_image - baseline

    if tokens_per_image <= 0:
        raise RuntimeError(
            f"Measured a non-positive per-image cost (baseline={baseline}, with_image={with_image}). "
            f"The provider may not report image tokens in the input-token count."
        )

    path = _write_tokens_per_image(player, tokens_per_image)
    _render(player, capabilities, baseline, with_image, tokens_per_image, path)


def _load_calibration_image(path: Path, *, capabilities: PlayerCapabilities) -> bytes:
    """Load and resize the explicit calibration PNG to the manual prompt's portrait dimensions."""
    resizer = ImageResizer(
        target_width=capabilities.image_dimensions.short_side,
        target_height=capabilities.image_dimensions.long_side,
    )
    image = resizer.resize_image(load_observation_from_bytes(path.read_bytes()))
    with io.BytesIO() as output:
        image.save(output, format="PNG")
        return output.getvalue()


async def _measure(agent: Agent, image_bytes: bytes) -> tuple[int, int]:
    """Return `(baseline_input_tokens, with_image_input_tokens)` for the same prompt.

    Starts from the agent's own `model_settings` and overrides only `max_tokens`, so the config's
    provider-correct thinking setting is preserved rather than clobbered. A per-request settings
    callable has no static value to start from, so we fall back to overriding just `max_tokens`.

    Both requests send the prompt as one-element multipart list, so the only difference
    between them is the image part. A plain-string baseline could tokenise differently and skew
    the delta.
    """
    base = None if callable(agent.model_settings) else agent.model_settings  # noqa: WPS504
    configured_max_tokens = (
        base.get("max_tokens") if base is not None else None  # noqa: WPS504
    )
    calibration_max_tokens = max(
        _CALIBRATION_MIN_MAX_TOKENS,
        configured_max_tokens if isinstance(configured_max_tokens, int) else 0,  # noqa: WPS504
    )
    settings = merge_model_settings(base, {"max_tokens": calibration_max_tokens})
    baseline = (await agent.run([_PROMPT], model_settings=settings)).usage.input_tokens
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

    Replaces the existing `tokens_per_image:` line if present, else inserts one just below
    `player_name:` (falling back to directly under the `capabilities:` header when there is no
    `player_name:`), matching the key order of the checked-in configs. Everything else is left
    byte-for-byte, so comments and `${oc.env:...}` interpolations survive.
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
    block = range(header + 1, _block_end(lines, header))
    player_name = next(
        (index for index in block if lines[index].lstrip().startswith("player_name:")), None
    )
    for index in block:
        if lines[index].lstrip().startswith("tokens_per_image:"):
            lines[index] = new_line
            break
    else:
        insert_at = header + 1 if player_name is None else player_name + 1
        lines.insert(insert_at, new_line)

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
