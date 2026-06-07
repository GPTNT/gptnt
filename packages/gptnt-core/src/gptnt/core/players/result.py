from typing import Generic, TypeVar

from pydantic import BaseModel, Field, field_validator
from pydantic_ai import BaseToolCallPart, BaseToolReturnPart, ModelMessage, ModelResponse, RunUsage

from gptnt.core.players.exceptions import AIResponseErrorType

ModelOutputT_co = TypeVar("ModelOutputT_co", covariant=True)


class AgentCallResult(BaseModel, Generic[ModelOutputT_co]):  # noqa: UP046
    """Result of an agent call."""

    output: ModelOutputT_co
    thoughts: str | None

    usage: RunUsage
    new_messages: list[ModelMessage]

    ai_response_error: list[AIResponseErrorType] = Field(default_factory=list)
    raw_output: str | None = None

    @field_validator("new_messages")
    @classmethod
    def check_no_tools_in_messages(cls, messages: list[ModelMessage]) -> list[ModelMessage]:
        """Ensure there are no tool parts in the new messages.

        We do this just to make life easier right now. But that also means we are double-ing down
        on the whole "no using function tools to play the game" aspect of the benchmark.

        Also Pydantic says to use ValueError and not TypeError, hence the noqa.
        """
        for message in messages:
            for part in message.parts:
                if isinstance(part, (BaseToolReturnPart, BaseToolCallPart)):
                    raise ValueError("Tool messages are not allowed in new_messages.")  # noqa: TRY004
        return messages

    @field_validator("new_messages")
    @classmethod
    def check_final_message_is_model_response(
        cls, messages: list[ModelMessage]
    ) -> list[ModelMessage]:
        """Ensure the final message is a ModelResponse."""
        if messages:
            final_message = messages[-1]
            if not isinstance(final_message, ModelResponse):
                raise ValueError("The final message in new_messages must be a ModelResponse.")
        return messages
