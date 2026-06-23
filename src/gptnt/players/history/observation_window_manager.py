import copy
from dataclasses import dataclass

import logfire
from pydantic_ai.messages import ModelMessage, ModelRequest

from gptnt.players.history.message_transformer import remove_binary_content_from_model_request
from gptnt.players.history.single_run import SingleRun
from gptnt.players.history.token_accountant import TokenAccountant


@dataclass(kw_only=True)
class ObservationWindowManager:
    """Manages observation window cleanup for message history runs.

    The observation window determines how many recent turns should retain their observations
    (BinaryContent). Older turns outside the window have observations removed to save token space.
    """

    window_length: int
    """Number of recent turns to preserve observations in."""

    token_accountant: TokenAccountant
    """Token accountant for updating token counts after observation removal."""

    @logfire.instrument("Apply observation window to runs", extract_args=False)
    def apply_window_to_runs(self, turn_runs: list[SingleRun]) -> list[SingleRun]:
        """Apply observation window cleanup to turn runs."""
        # If the window length is <= 0, this is handled when messages are provided to the
        # MessageHistory itself, so we can skip processing here.
        if not turn_runs or self.window_length <= 0:
            return turn_runs

        # Calculate how many runs fall outside the observation window
        # If window_length is 0, all runs are outside the window
        # If window_length >= len(runs), no runs are outside
        runs_to_clean = turn_runs[: -self.window_length]

        if not runs_to_clean:
            return turn_runs

        # Clean observations from runs outside the window
        cleaned_runs = [
            self.clean_observations_from_run(run, keep_last=False) for run in runs_to_clean
        ]

        # Return cleaned runs + runs still in window (unchanged)
        return cleaned_runs + turn_runs[-self.window_length :]

    def clean_observations_from_run(self, run: SingleRun, *, keep_last: bool = False) -> SingleRun:
        """Remove observations from a single run.

        Args:
            run: The run to clean
            keep_last: Whether to keep the last observation in each message

        Returns:
            A new SingleRun with observations removed and tokens updated
        """
        new_run = copy.deepcopy(run)
        cleaned_messages, num_removed = self.remove_observations_from_messages(
            new_run.messages, keep_last_observation=keep_last
        )
        new_run.messages = cleaned_messages

        # Update token count if observations were removed
        if num_removed > 0:
            new_run.input_tokens = self.token_accountant.deduct_observations(
                num_removed, run_input_tokens=new_run.input_tokens
            )

        return new_run

    def remove_observations_from_messages(
        self, messages: list[ModelMessage], *, keep_last_observation: bool = True
    ) -> tuple[list[ModelMessage], int]:
        """Remove observations (BinaryContent) from messages.

        Args:
            messages: List of messages to process
            keep_last_observation: If True, keeps the last observation in each message

        Returns:
            Tuple of (cleaned messages, number of observations removed)
        """
        updated_messages: list[ModelMessage] = []
        num_observations_removed = 0

        for message in messages:
            if isinstance(message, ModelRequest):
                num_removed, clean_message = remove_binary_content_from_model_request(
                    message, keep_last_observation=keep_last_observation
                )
                num_observations_removed += num_removed
                updated_messages.append(clean_message)
            else:
                updated_messages.append(message)

        return updated_messages, num_observations_removed
