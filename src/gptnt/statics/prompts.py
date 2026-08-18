from gptnt.players.specification import ThinkingMethod
from gptnt.statics.constants import (
    GROUNDING_HALLUCINATION_TYPE_A_RESPONSE,
    GROUNDING_HALLUCINATION_TYPE_B_RESPONSE,
)

THINKING_OUT_LOUD_PROMPT = "Reason about your task before choosing an answer. Keep your reasoning concise, using as few words and sentences as possible. Avoid redundancy and do not get stuck in circular reasoning loops. Provide your reasoning first, followed by your chosen answer using the format '<thought>{REASONING}</thought><action>{ANSWER}</action>', replacing {REASONING} with your reasoning and {ANSWER} with your chosen answer."

INNER_MONOLOGUE_PROMPT = "Reason internally about your task before choosing an answer. Keep your reasoning concise, avoid redundancy, and do not get stuck in circular reasoning loops. Do not include your reasoning or any reasoning tags in the response. Output only the chosen answer in the required format."

OPEN_ENDED_INSTRUCTION = "Answer the following question based on given context. Output only the one letter, word, short phrase, or number required to answer the question, nothing else."
MCQ_INSTRUCTION = "Answer the following multiple choice question based on the given context. Output only the letter of the correct answer, nothing else."
OCR_INSTRUCTION = "Follow the instruction given the context from the image. Output only the answer as unformatted text, nothing else."


GROUNDING_HALLUCINATION_PROMPT = f'2. If multiple valid targets exist: "{GROUNDING_HALLUCINATION_TYPE_A_RESPONSE}".\n\n3. If no valid target exists: "{GROUNDING_HALLUCINATION_TYPE_B_RESPONSE}".'


GROUNDING_SOM_PROMPT = (
    "The screenshot contains objects annotated with alphabetical markers positioned beside each clickable UI element. To click on the element specified by the user, respond only with the corresponding letter.\n\nAnswer Format: Respond with exactly one of the following:\n\n1. If the target is found: Return only the letter marking the element.\n\n"
    + GROUNDING_HALLUCINATION_PROMPT
)

GROUNDING_COORDINATES_PROMPT = (
    'The resolution of the screen is {IMAGE_WIDTH}x{IMAGE_HEIGHT} pixels.\nCoordinates are measured from the top-left corner: x (pixels from left edge), y (pixels from top edge).\nTo click on the UI element specified by the user, identify a pixel coordinate that falls within the element.\n\nAnswer Format: Respond with exactly one of the following:\n\n1. If the target is found: Return exactly one JSON object with exactly two integer fields, x and y, in this format: {"x": 468, "y": 535}. Do not return arrays, a bounding box, a tuple, function-call syntax, or more than one coordinate.\n\n'
    + GROUNDING_HALLUCINATION_PROMPT
)


def build_grounding_normalised_coordinates_prompt(coordinate_scale: int = 1000) -> str:
    """Build grounding instructions using the model's native normalised coordinate scale."""
    example_coordinate = round(coordinate_scale * 0.468)
    return (
        "Coordinates are normalised independently along each axis to integers from 0 to "
        f'{coordinate_scale}. The top-left corner is {{"x": 0, "y": 0}} and the '
        f'bottom-right corner is {{"x": {coordinate_scale}, "y": {coordinate_scale}}}.\n'
        "To click on the UI element specified by the user, identify a normalised coordinate that "
        "falls within the element.\n\nAnswer Format: Respond with exactly one of the following:\n\n"
        "1. If the target is found: Return exactly one JSON object with exactly two integer "
        f'fields, x and y, in this format: {{"x": {example_coordinate}, "y": '
        f"{round(coordinate_scale * 0.535)}}}. Do not return arrays, a bounding box, a tuple, "
        "function-call syntax, or more than one coordinate.\n\n" + GROUNDING_HALLUCINATION_PROMPT
    )


GROUNDING_NORMALISED_COORDINATES_PROMPT = build_grounding_normalised_coordinates_prompt()


def format_instruction_with_reasoning(
    instruction: str, *, allow_thinking: bool, thinking_method: ThinkingMethod
) -> str:
    """Prepend the appropriate reasoning prompt to the instruction."""
    if not allow_thinking:
        return instruction

    reasoning_prompt = (
        INNER_MONOLOGUE_PROMPT
        if thinking_method == "inner-monologue"
        else THINKING_OUT_LOUD_PROMPT
    )
    return f"{reasoning_prompt} {instruction}"
