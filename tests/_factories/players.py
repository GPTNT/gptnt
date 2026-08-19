"""Shared player values for tests whose subject is not configuration composition."""

from gptnt.players.specification import PlayerModelConfiguration

TEST_MODEL_CONFIGURATION = PlayerModelConfiguration(
    name="function:test-model", provider="function", settings={}
)
