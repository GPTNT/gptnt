import pytest
from pytest_cases import param_fixture

from gptnt.core.ktane.actions import GameActionType
from gptnt.core.players.actions import InteractGameAction, PlayerOutputType
from gptnt.core.players.locations import PixelLocation, ScaledLocation
from gptnt.core.specification import PlayerCapabilities

interaction_location_method = param_fixture(
    "interaction_location_method", ["set-of-marks", "coordinates"]
)


@pytest.fixture
def capabilities(interaction_location_method: str) -> PlayerCapabilities:
    """Fixture for PlayerCapabilities with varying interaction location methods."""
    return PlayerCapabilities(
        player_name="test_player",
        player_type="ai",
        structured_output_mode="prompted",
        max_observations_per_request=16,
        interaction_location_method=interaction_location_method,
    )


class CapabilitiesCases:
    def case_prompted_set_of_marks(self) -> PlayerCapabilities:
        return PlayerCapabilities(
            player_name="test_player",
            player_type="ai",
            structured_output_mode="prompted",
            interaction_location_method="set-of-marks",
            thinking_method="inner-monologue",
        )

    def case_prompted_absolute_coordinates(self) -> PlayerCapabilities:
        return PlayerCapabilities(
            player_name="test_player",
            player_type="ai",
            structured_output_mode="prompted",
            interaction_location_method="coordinates",
            thinking_method="inner-monologue",
            coordinate_mode="absolute",
        )

    def case_prompted_normalised_coordinates(self) -> PlayerCapabilities:
        return PlayerCapabilities(
            player_name="test_player",
            player_type="ai",
            structured_output_mode="prompted",
            interaction_location_method="coordinates",
            thinking_method="inner-monologue",
            coordinate_mode="normalised",
        )

    def case_react_set_of_marks(self) -> PlayerCapabilities:
        return PlayerCapabilities(
            player_name="test_player",
            player_type="ai",
            structured_output_mode=None,
            interaction_location_method="set-of-marks",
            thinking_method="thinking-out-loud",
        )

    def case_react_absolute_coordinates(self) -> PlayerCapabilities:
        return PlayerCapabilities(
            player_name="test_player",
            player_type="ai",
            structured_output_mode=None,
            interaction_location_method="coordinates",
            thinking_method="thinking-out-loud",
            coordinate_mode="absolute",
        )

    def case_react_normalised_coordinates(self) -> PlayerCapabilities:
        return PlayerCapabilities(
            player_name="test_player",
            player_type="ai",
            structured_output_mode=None,
            interaction_location_method="coordinates",
            thinking_method="thinking-out-loud",
            coordinate_mode="normalised",
        )

    @staticmethod
    def check_expected_output_with_capabilities(  # noqa: WPS602
        expected_output: PlayerOutputType | str, capabilities: PlayerCapabilities
    ) -> None:
        """Check if the expected output is compatible with the given capabilities."""
        invalid_test_combinations = [
            (
                capabilities.interaction_location_method == "coordinates"
                and capabilities.coordinate_mode == "absolute"
                and isinstance(expected_output, InteractGameAction)
                and expected_output.action in GameActionType.require_location()
                and not isinstance(expected_output.location, PixelLocation)
            ),
            (
                capabilities.interaction_location_method == "coordinates"
                and capabilities.coordinate_mode == "normalised"
                and isinstance(expected_output, InteractGameAction)
                and expected_output.action in GameActionType.require_location()
                and not isinstance(expected_output.location, ScaledLocation)
            ),
            (
                capabilities.interaction_location_method == "set-of-marks"
                and isinstance(expected_output, InteractGameAction)
                and expected_output.action in GameActionType.require_location()
                and not isinstance(expected_output.location, (str, int))
            ),
        ]
        if any(invalid_test_combinations):
            pytest.skip("Skip invalid test case")
