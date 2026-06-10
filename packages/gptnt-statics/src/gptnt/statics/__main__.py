from gptnt.core.common.typer import AsyncTyper
from gptnt.statics.cli.defuser_grounding_coordinates import run_defuser_grounding_evaluation
from gptnt.statics.cli.defuser_grounding_som import run_defuser_set_of_marks_evaluation
from gptnt.statics.cli.defuser_vqa_mcq import run_defuser_mcq_vqa_evaluation
from gptnt.statics.cli.defuser_vqa_oe import run_defuser_oe_vqa_evaluation
from gptnt.statics.cli.expert_element_grounding import run_expert_grounding_evaluation
from gptnt.statics.cli.expert_ocr import (
    run_expert_ocr_evaluation,
    run_expert_ocr_with_text_evaluation,
)
from gptnt.statics.cli.expert_vqa import (
    run_expert_vqa_evaluation,
    run_expert_vqa_no_manual_evaluation,
)

statics_app = AsyncTyper(
    name="statics",
    help="Run static evaluations against HuggingFace datasets.",
    no_args_is_help=True,
    rich_help_panel="Statics",
)

_ = statics_app.command("defuser-grounding-coordinates")(run_defuser_grounding_evaluation)
_ = statics_app.command("defuser-grounding-som")(run_defuser_set_of_marks_evaluation)
_ = statics_app.command("defuser-vqa-oe")(run_defuser_oe_vqa_evaluation)
_ = statics_app.command("defuser-vqa-mcq")(run_defuser_mcq_vqa_evaluation)
_ = statics_app.command("expert-vqa")(run_expert_vqa_evaluation)
_ = statics_app.command("expert-vqa-no-manual", help="Expert VQA evaluation without manual.")(
    run_expert_vqa_no_manual_evaluation
)
_ = statics_app.command("expert-ocr")(run_expert_ocr_evaluation)
_ = statics_app.command("expert-ocr-with-text")(run_expert_ocr_with_text_evaluation)
_ = statics_app.command("expert-element-grounding")(run_expert_grounding_evaluation)
