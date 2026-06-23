import anyio
from cyclopts import App

statics_app = App(name="statics", help="Run static evaluations against HuggingFace datasets.")

statics_app.command(
    "gptnt.cli.statics.defuser_grounding_coordinates:run_defuser_grounding_evaluation",
    name="defuser-grounding-coordinates",
    help="Defuser grounding using absolute coordinates.",
)
statics_app.command(
    "gptnt.cli.statics.defuser_grounding_som:run_defuser_set_of_marks_evaluation",
    name="defuser-grounding-som",
    help="Defuser grounding using Set of Marks.",
)
statics_app.command(
    "gptnt.cli.statics.defuser_vqa_oe:run_defuser_oe_vqa_evaluation",
    name="defuser-vqa-oe",
    help="Defuser VQA open-ended questions.",
)
statics_app.command(
    "gptnt.cli.statics.defuser_vqa_mcq:run_defuser_mcq_vqa_evaluation",
    name="defuser-vqa-mcq",
    help="Defuser VQA multiple choice questions.",
)
statics_app.command(
    "gptnt.cli.statics.expert_vqa:run_expert_vqa_evaluation",
    name="expert-vqa",
    help="Expert VQA evaluation.",
)
statics_app.command(
    "gptnt.cli.statics.expert_vqa:run_expert_vqa_no_manual_evaluation",
    name="expert-vqa-no-manual",
    help="Expert VQA evaluation without manual.",
)
statics_app.command(
    "gptnt.cli.statics.expert_ocr:run_expert_ocr_evaluation",
    name="expert-ocr",
    help="Expert OCR evaluation.",
)
statics_app.command(
    "gptnt.cli.statics.expert_ocr:run_expert_ocr_with_text_evaluation",
    name="expert-ocr-with-text",
    help="Expert OCR evaluation with the image AND the text.",
)
statics_app.command(
    "gptnt.cli.statics.expert_element_grounding:run_expert_grounding_evaluation",
    name="expert-element-grounding",
    help="Expert element grounding evaluation.",
)
statics_app.command(
    "gptnt.cli.statics.how_do_you:run_how_do_you_evaluation",
    name="how-do-you",
    help='Run the simple "How do you..." evaluation.',
)


def main() -> None:
    """Entry point for the `gptnt statics` command."""
    anyio.run(statics_app.run_async)


if __name__ == "__main__":
    main()
