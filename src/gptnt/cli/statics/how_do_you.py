from collections import defaultdict
from typing import Annotated

from cyclopts import Parameter
from cyclopts.types import PositiveInt
from pydantic_core import to_json
from structlog import get_logger

from gptnt.cli.statics._config_loader import ConfigLoader
from gptnt.cli.statics._fields import AllowThinkingOption, ModelOption, ProviderOption
from gptnt.common.logger import create_progress
from gptnt.common.paths import Paths
from gptnt.ktane.state.modules import KtaneComponent
from gptnt.players.reasoning_parser.inner_monologue import InnerMonologueReasoningParser
from gptnt.players.reasoning_parser.react import ReactStyleReasoningParser
from gptnt.statics.evaluation.constants import MODULE_NAMES, get_valid_modules
from gptnt.statics.evaluation.model import EvalModel
from gptnt.statics.evaluation.prompts import format_instruction_with_reasoning

logger = get_logger()
paths = Paths()

QUESTION = "How do you solve the {module} module in KTANE?"


def create_prompts() -> dict[KtaneComponent, str]:
    """Create prompts for each module."""
    valid_modules = get_valid_modules()
    prompts = {module: QUESTION.format(module=MODULE_NAMES[module]) for module in valid_modules}
    return prompts


async def run_how_do_you_evaluation(  # noqa: WPS210
    *,
    model: ModelOption,
    provider: ProviderOption = None,
    attempts: Annotated[PositiveInt, Parameter(help="Number of attempts for each component.")] = 1,
    allow_thinking: AllowThinkingOption = False,
    output_file_prefix: str | None = None,
) -> None:
    """Run the simple "How do you..." evaluation."""
    config_loader = ConfigLoader(model=model, provider=provider, role="defuser")
    eval_model = EvalModel.from_agent(agent=config_loader.agent_fn())
    eval_model.update_reasoning_parser(
        InnerMonologueReasoningParser()
        if config_loader.capabilities.thinking_method == "inner-monologue"
        else ReactStyleReasoningParser()
    )
    prompts = create_prompts()

    all_results = defaultdict(list)
    with create_progress(extra_fields=["extra"]) as progress:
        task = progress.add_task("Running evaluation...", total=len(prompts) * attempts)
        for component, prompt in prompts.items():
            for attempt in range(attempts):
                formatted_prompt = format_instruction_with_reasoning(
                    instruction=prompt,
                    allow_thinking=allow_thinking,
                    thinking_method=config_loader.capabilities.thinking_method,
                ).strip()
                response = await eval_model.model_predict([formatted_prompt])  # noqa: WPS476
                all_results[component].append({"prompt": formatted_prompt, "response": response})
                progress.update(
                    task, advance=1, extra=f"Component: {component}, Attempt: {attempt + 1}"
                )

    output_file = paths.output.joinpath("how_do_you").joinpath(f"{eval_model.name}.json")
    if output_file_prefix is not None:
        output_file = output_file.with_stem(f"{output_file_prefix}_{output_file.stem}")
    output_file.parent.mkdir(parents=True, exist_ok=True)
    _ = output_file.write_bytes(to_json(all_results))
    logger.info(f"Saved results to {output_file}")
