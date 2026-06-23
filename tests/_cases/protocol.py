import pytest
from pytest_cases import fixture

from gptnt.players.actions import InteractGameAction, PlayerOutputType, SendMessageAction
from gptnt.specification import PlayerProtocol


class ProtocolCases:
    """Comprehensive PlayerProtocol configurations consolidating various test scenarios."""

    def case_defuser(self) -> PlayerProtocol:
        """Defuser role, collaborative, without manual."""
        return PlayerProtocol(
            role="defuser",
            communication_style="sync",
            is_playing_alone=False,
            include_manual=False,
        )

    def case_defuser_with_manual(self) -> PlayerProtocol:
        """Defuser role, collaborative, with manual."""
        return PlayerProtocol(
            role="defuser", communication_style="sync", is_playing_alone=False, include_manual=True
        )

    def case_solo_defuser(self) -> PlayerProtocol:
        """Solo defuser, playing alone, without manual."""
        return PlayerProtocol(
            role="defuser", communication_style="sync", is_playing_alone=True, include_manual=False
        )

    def case_expert(self) -> PlayerProtocol:
        """Expert role with manual."""
        return PlayerProtocol(
            role="expert", communication_style="sync", is_playing_alone=False, include_manual=True
        )

    @staticmethod
    def check_expected_output_with_protocol(  # noqa: WPS602
        expected_output: PlayerOutputType | str, protocol: PlayerProtocol
    ) -> None:
        """Check if the expected output is compatible with the given protocol."""
        invalid_test_combinations = [
            (isinstance(expected_output, SendMessageAction) and protocol.is_playing_alone),
            (isinstance(expected_output, InteractGameAction) and protocol.role == "expert"),
        ]
        if any(invalid_test_combinations):
            pytest.skip("The expected output is not compatible with the given protocol.")


@fixture
def defuser_protocol() -> PlayerProtocol:
    """Create a defuser protocol."""
    return PlayerProtocol(
        role="defuser", include_manual=False, is_playing_alone=False, communication_style="sync"
    )


@fixture
def expert_protocol() -> PlayerProtocol:
    """Create an expert protocol."""
    return PlayerProtocol(
        role="expert", include_manual=False, is_playing_alone=False, communication_style="sync"
    )
