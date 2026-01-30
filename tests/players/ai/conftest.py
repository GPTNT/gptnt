from gptnt.ktane.actions import GameActionType
from gptnt.players.actions import (
    AbsoluteCoordinate,
    DoNothingAction,
    InteractGameAction,
    SendMessageAction,
    SingleAlphabetLetter,
)


class SuccessfulOutputCases:
    """Case class for successful model outputs."""

    def case_do_nothing_action(self) -> DoNothingAction:
        """DoNothingAction output."""
        return DoNothingAction()

    def case_send_message_action(self) -> SendMessageAction:
        """SendMessageAction output."""
        return SendMessageAction(message="This is a test message")

    def case_send_message_with_special_chars(self) -> SendMessageAction:
        """SendMessageAction with special characters."""
        return SendMessageAction(message="Hello! How are you? I'm doing great.")

    def case_interact_game_set_of_marks(self) -> InteractGameAction[SingleAlphabetLetter]:
        """InteractGameAction with set-of-marks location."""
        return InteractGameAction[SingleAlphabetLetter](
            action=GameActionType.click_release, location="A"
        )

    def case_interact_game_absolute_coordinate(self) -> InteractGameAction[AbsoluteCoordinate]:
        """InteractGameAction with absolute coordinate."""
        return InteractGameAction[AbsoluteCoordinate](
            action=GameActionType.click_release, location=AbsoluteCoordinate(x=100, y=200)
        )
