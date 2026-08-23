from typing import Generic, Self, TypeVar

from pydantic import BaseModel, Field, field_validator
from pydantic_ai import BaseToolCallPart, BaseToolReturnPart, ModelMessage, ModelResponse, RunUsage
from whenever import Instant

from gptnt.players.exceptions import AIResponseErrorType

ModelOutputT_co = TypeVar("ModelOutputT_co", covariant=True)


class AgentCallResult(BaseModel, Generic[ModelOutputT_co]):  # noqa: UP046
    """Result of an agent call."""

    output: ModelOutputT_co
    thoughts: str | None

    usage: RunUsage
    new_messages: list[ModelMessage]
    """Tool-free request and response messages ending in the call's final model response."""

    ai_response_error: list[AIResponseErrorType] = Field(default_factory=list)
    """Response-error classifications retained after parsing or recovery."""

    raw_output: str | None = None

    @field_validator("new_messages")
    @classmethod
    def check_no_tools_in_messages(cls, messages: list[ModelMessage]) -> list[ModelMessage]:
        """Ensure there are no tool parts in the new messages.

        We do this just to make life easier right now. But that also means we are double-ing down
        on "no using function tools to play the game" aspect of the benchmark.

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


class DispatchedAgentCallResult(AgentCallResult[ModelOutputT_co], Generic[ModelOutputT_co]):  # noqa: UP046
    """Agent result stamped when dispatch of its output begins."""

    dispatched_at: Instant
    """Instant when output dispatch starts and the origin for the recorded step timestamp."""

    @classmethod
    def from_agent_call(cls, agent_call_result: AgentCallResult[ModelOutputT_co]) -> Self:
        """Copy an agent result and stamp it with the current time.

        Since we are copying an existing `AgentCallResult`, we use `model_construct` to avoid
        re-validating the object.
        """
        return cls.model_construct(
            output=agent_call_result.output,
            thoughts=agent_call_result.thoughts,
            usage=agent_call_result.usage,
            new_messages=agent_call_result.new_messages,
            ai_response_error=agent_call_result.ai_response_error,
            raw_output=agent_call_result.raw_output,
            dispatched_at=Instant.now(),
        )
