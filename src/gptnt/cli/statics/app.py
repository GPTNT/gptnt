from gptnt.common.typer import LazyAsyncGroup

statics_app = LazyAsyncGroup(
    name="statics",
    help="Run static evaluations against HuggingFace datasets.",
    no_args_is_help=True,
    rich_help_panel="Statics",
)

statics_app.lazy_add(
    "defuser-grounding-coordinates",
    "gptnt.cli.statics.defuser_grounding_coordinates",
    "run_defuser_grounding_evaluation",
    "Defuser grounding using absolute coordinates.",
)
statics_app.lazy_add(
    "defuser-grounding-som",
    "gptnt.cli.statics.defuser_grounding_som",
    "run_defuser_set_of_marks_evaluation",
    "Defuser grounding using Set of Marks.",
)
statics_app.lazy_add(
    "defuser-vqa-oe",
    "gptnt.cli.statics.defuser_vqa_oe",
    "run_defuser_oe_vqa_evaluation",
    "Defuser VQA open-ended questions.",
)
statics_app.lazy_add(
    "defuser-vqa-mcq",
    "gptnt.cli.statics.defuser_vqa_mcq",
    "run_defuser_mcq_vqa_evaluation",
    "Defuser VQA multiple choice questions.",
)
statics_app.lazy_add(
    "expert-vqa",
    "gptnt.cli.statics.expert_vqa",
    "run_expert_vqa_evaluation",
    "Expert VQA evaluation.",
)
statics_app.lazy_add(
    "expert-ocr",
    "gptnt.cli.statics.expert_ocr",
    "run_expert_ocr_evaluation",
    "Expert OCR evaluation.",
)
statics_app.lazy_add(
    "expert-element-grounding",
    "gptnt.cli.statics.expert_element_grounding",
    "run_expert_grounding_evaluation",
    "Expert element grounding evaluation.",
)
