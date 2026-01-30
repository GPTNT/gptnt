from hypothesis import given, strategies as st
from pydantic_ai import RunUsage

from gptnt.players.actions import AgentCallResult, DoNothingAction, PlayerOutputType
from gptnt.players.exceptions import AIResponseErrorType
from gptnt.players.feedback.nobf import NaughtyOutputBehaviourFeedbackGenerator


@given(
    error_list=st.lists(
        st.sampled_from(list(AIResponseErrorType)).filter(
            lambda error: error is not AIResponseErrorType.guardrail_violation
        ),
        min_size=1,
        max_size=5,
    )
)
def test_nobf_generator_handles_error_combinations(error_list: list[AIResponseErrorType]) -> None:
    """Test that the NaughtyOutputBehaviourFeedbackGenerator can handle combinations of errors."""
    generator = NaughtyOutputBehaviourFeedbackGenerator()

    # Create a mock AgentCallResult with the given errors
    agent_call_result = AgentCallResult[PlayerOutputType](
        ai_response_error=error_list,
        output=DoNothingAction(),
        thoughts=None,
        usage=RunUsage(),
        new_messages=[],
    )

    feedback = generator.generate(agent_call_result=agent_call_result)

    assert feedback is not None
    feedback_without_tags = (
        feedback.replace(f"<{generator.feedback_xml_tag}>", "")
        .replace(f"</{generator.feedback_xml_tag}>", "")
        .strip()
    )
    assert feedback_without_tags


def test_nobf_generator_handles_no_errors() -> None:
    generator = NaughtyOutputBehaviourFeedbackGenerator()

    # Create a mock AgentCallResult with the given errors
    agent_call_result = AgentCallResult[PlayerOutputType](
        ai_response_error=[],
        output=DoNothingAction(),
        thoughts=None,
        usage=RunUsage(),
        new_messages=[],
    )

    feedback = generator.generate(agent_call_result=agent_call_result)

    assert feedback is None


def test_nobf_generator_handles_guardrail_violation() -> None:
    generator = NaughtyOutputBehaviourFeedbackGenerator()

    # Create a mock AgentCallResult with guardrail violation error
    agent_call_result = AgentCallResult[PlayerOutputType](
        ai_response_error=[AIResponseErrorType.guardrail_violation],
        output=DoNothingAction(),
        thoughts=None,
        usage=RunUsage(),
        new_messages=[],
    )

    feedback = generator.generate(agent_call_result=agent_call_result)

    assert feedback is None
