from difflib import get_close_matches
from typing import Annotated

from cyclopts import Parameter

from gptnt.cli.config_discovery import discover_players, discover_providers

_PLAYER_GROUP = "Player"


def _reject_unknown(name: str, known: list[str], *, kind: str, list_command: str) -> None:
    """Raise a `gptnt list`-pointing error when `name` matches no config on disk."""
    if name in known:
        return
    closest = get_close_matches(name, known, n=1)
    suggestion = f" Did you mean {closest[0]!r}?" if closest else ""
    raise ValueError(f"unknown {kind} {name!r}.{suggestion} See `{list_command}`.")


def _validate_player(_type: object, name: str) -> None:
    """Validate a `--player` against the discovered player configs."""
    _reject_unknown(name, discover_players(), kind="player", list_command="gptnt list players")


def _validate_provider(_type: object, name: str | None) -> None:
    """Validate a `--provider` against the discovered provider configs, allowing the default."""
    if name is None:
        return
    _reject_unknown(name, discover_providers(), kind="provider", list_command="gptnt list players")


PlayerOption = Annotated[
    str,
    Parameter(
        name="--player",
        help="Player config name (under `configs/player/<name>.yaml`).",
        group=_PLAYER_GROUP,
        validator=_validate_player,
    ),
]

ProviderOption = Annotated[
    str | None,
    Parameter(
        name="--provider",
        help="Provider config override (under `configs/player/provider/<name>.yaml`).",
        group=_PLAYER_GROUP,
        validator=_validate_provider,
    ),
]
