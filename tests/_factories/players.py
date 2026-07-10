"""Builders for player-shaped test objects (protocols, capabilities)."""

from __future__ import annotations

from gptnt.players.specification import (
    CommunicationStyle,
    PlayerCapabilities,
    PlayerProtocol,
    PlayerRole,
    PlayerType,
)


def make_protocol(
    *,
    role: PlayerRole = "defuser",
    communication_style: CommunicationStyle = "sync",
    is_playing_alone: bool = True,
    include_manual: bool = False,
    receive_feedback_after_action: bool = False,
    allow_magic_actions: bool = False,
    allow_lottery_actions: bool = False,
) -> PlayerProtocol:
    """A real PlayerProtocol; a solo defuser by default (an expert must set is_playing_alone)."""
    return PlayerProtocol(
        role=role,
        communication_style=communication_style,
        is_playing_alone=is_playing_alone,
        include_manual=include_manual,
        receive_feedback_after_action=receive_feedback_after_action,
        allow_magic_actions=allow_magic_actions,
        allow_lottery_actions=allow_lottery_actions,
    )


def make_capabilities(
    *, player_name: str = "test-player", player_type: PlayerType = "ai"
) -> PlayerCapabilities:
    """A real PlayerCapabilities; every field past the name and type keeps its model default."""
    return PlayerCapabilities(player_name=player_name, player_type=player_type)
