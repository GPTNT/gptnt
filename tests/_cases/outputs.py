from pytest_cases import param_fixture

from gptnt.core.ktane.actions import GameActionType, RelativeCoordinate
from gptnt.core.players.actions import DoNothingAction, InteractGameAction, SendMessageAction
from gptnt.core.players.locations import PixelLocation, ScaledLocation, SingleAlphabetLetter

game_command = param_fixture(
    "game_command", list(GameActionType), ids=[action.value for action in GameActionType]
)


class PredictedActionCases:
    """Case class for successful model outputs across various action types."""

    def case_do_nothing(self) -> DoNothingAction:
        """DoNothingAction output."""
        return DoNothingAction()

    def case_send_message(self) -> SendMessageAction:
        """SendMessageAction output."""
        return SendMessageAction(message="This is a test message")

    def case_send_message_with_special_chars(self) -> SendMessageAction:
        """SendMessageAction with special characters."""
        return SendMessageAction(message="Hello! How are you? I'm doing great.")

    def case_interact_set_of_marks(
        self, game_command: GameActionType
    ) -> InteractGameAction[SingleAlphabetLetter]:
        """InteractGameAction with set-of-marks location."""
        return InteractGameAction[SingleAlphabetLetter](
            action=game_command,
            location="A" if game_command in GameActionType.require_location() else None,
        )

    def case_interact_relative_coordinate(
        self, game_command: GameActionType
    ) -> InteractGameAction[RelativeCoordinate]:
        return InteractGameAction[RelativeCoordinate](
            action=game_command,
            location=RelativeCoordinate(x_pos=0.5, y_pos=0.5)
            if game_command in GameActionType.require_location()
            else None,
        )

    def case_interact_absolute_coordinate(
        self, game_command: GameActionType
    ) -> InteractGameAction[PixelLocation]:
        """InteractGameAction with absolute coordinate."""
        return InteractGameAction[PixelLocation](
            action=game_command,
            location=PixelLocation(x=100, y=200)
            if game_command in GameActionType.require_location()
            else None,
        )

    def case_interact_normalised_coordinate(
        self, game_command: GameActionType
    ) -> InteractGameAction[ScaledLocation]:
        """InteractGameAction with normalised coordinate."""
        return InteractGameAction[ScaledLocation](
            action=game_command,
            location=ScaledLocation(x=500, y=750)
            if game_command in GameActionType.require_location()
            else None,
        )


class ReflectionOutputCases:
    """Case class for different reflection output scenarios."""

    message = "I need to be better."

    def case_full_schema(self) -> str:
        return SendMessageAction(message=self.message).text_part_dump()

    def case_only_action(self) -> str:
        return SendMessageAction(message=self.message).model_dump_json()

    def case_string_output(self) -> str:
        return self.message
