from gptnt.specification import ThinkingMethod
from gptnt.statics.generation.defuser_vqa.constants import (
    GROUNDING_HALLUCINATION_TYPE_A_RESPONSE,
    GROUNDING_HALLUCINATION_TYPE_B_RESPONSE,
)

REASONING_PROMPT = "Reason about your task before choosing an answer. Keep your thoughts concise, using as few words and sentences as possible. Avoid redundancy and do not get stuck in circular reasoning loops. Provide your reasoning first, followed by your chosen answer using the format '<thought>{REASONING}</thought><action>{ANSWER}</action>', replacing {REASONING} with your reasoning and {ANSWER} with your chosen answer."

OPEN_ENDED_INSTRUCTION = "Answer the following question based on given context. Output only the one letter, word, short phrase, or number required to answer the question, nothing else."
MCQ_INSTRUCTION = "Answer the following multiple choice question based on the given context. Output only the letter of the correct answer, nothing else."
OCR_INSTRUCTION = "Follow the instruction given the context from the image. Output only the answer as unformatted text, nothing else."


GROUNDING_HALLUCINATION_PROMPT = f'2. If multiple valid targets exist: "{GROUNDING_HALLUCINATION_TYPE_A_RESPONSE}".\n\n3. If no valid target exists: "{GROUNDING_HALLUCINATION_TYPE_B_RESPONSE}".'


GROUNDING_SOM_PROMPT = (
    "The screenshot contains objects annotated with alphabetical markers positioned beside each clickable UI element. To click on the element specified by the user, respond only with the corresponding letter.\n\nAnswer Format: Respond with exactly one of the following:\n\n1. If the target is found: Return only the letter marking the element.\n\n"
    + GROUNDING_HALLUCINATION_PROMPT
)

GROUNDING_COORDINATES_PROMPT = (
    'The resolution of the screen is {IMAGE_WIDTH}x{IMAGE_HEIGHT} pixels.\nCoordinates are measured from the top-left corner: x (pixels from left edge), y (pixels from top edge).\nTo click on the UI element specified by the user, identify a (x, y) pixel coordinate that falls within the element.\n\nAnswer Format: Respond with exactly one of the following:\n\n1. If the target is found: Return a JSON with the coordinate: {"x": <int>, "y": <int>}.\n\n'
    + GROUNDING_HALLUCINATION_PROMPT
)


def format_instruction_with_reasoning(
    instruction: str, *, allow_thinking: bool, thinking_method: ThinkingMethod
) -> str:
    """Prepend the appropriate reasoning prompt to the instruction."""
    if not allow_thinking:
        return instruction

    reasoning_prompt = REASONING_PROMPT
    if thinking_method == "inner-monologue":
        reasoning_prompt = (
            REASONING_PROMPT.replace("<thought>", "<think>")
            .replace("</thought>", "</think>")
            .replace("reasoning", "thinking process")
        )
    return f"{reasoning_prompt} {instruction}"
