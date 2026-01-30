from functools import lru_cache
from textwrap import dedent

import structlog
from pydantic_ai import PromptedOutput
from pydantic_ai._output import OutputSchema, PromptedOutputSchema
from pydantic_ai.tools import RunContext

from gptnt.common.paths import Paths
from gptnt.players.specification import PlayerDeps, PlayerProtocol
from gptnt.prompts.prompt_cache import PromptCache

paths = Paths()

logger = structlog.get_logger()


class NoPromptForProtocolError(ValueError):
    """Exception raised when no prompt is found for the given player protocol."""

    def __init__(self, protocol: PlayerProtocol, *, prompt_category: str) -> None:
        super().__init__(f"No {prompt_category} prompt found for protocol: {protocol}")
        self.protocol = protocol
        self.prompt_category = prompt_category


@lru_cache
def _load_scenario(deps: PlayerDeps) -> str:
    """Load the scenario for the given protocol."""
    if deps.protocol.is_playing_alone:
        logger.debug("Loading scenario for solo")
        return PromptCache.get_text(paths.prompts.joinpath("scenario_solo.md"))

    logger.debug("Loading scenario for multiplayer")
    return PromptCache.get_text(paths.prompts.joinpath("scenario.md"))


@lru_cache
def _load_role(deps: PlayerDeps) -> str:
    """Load the role for the given protocol."""
    if deps.protocol.role == "expert" and not deps.protocol.is_playing_alone:
        return PromptCache.get_text(paths.prompts.joinpath("roles_expert.md"))
    if deps.protocol.role == "defuser" and not deps.protocol.is_playing_alone:
        return PromptCache.get_text(paths.prompts.joinpath("roles_defuser.md"))
    if deps.protocol.role == "defuser" and deps.protocol.is_playing_alone:
        path = (
            "roles_defuser_solo-player.md"
            if deps.protocol.include_manual
            else "roles_defuser_solo-defuser.md"
        )
        return PromptCache.get_text(paths.prompts.joinpath(path))

    raise NoPromptForProtocolError(deps.protocol, prompt_category="role")


@lru_cache
def _load_reasoning(deps: PlayerDeps) -> str:
    """Load the reasoning section for the given protocol."""
    reasoning = PromptCache.get_text(paths.prompts.joinpath("reasoning.md"))
    tag_format = PromptCache.get_text(
        paths.prompts.joinpath(
            "reasoning_thinking-out-loud.md"
            if deps.capabilities.thinking_method == "thinking-out-loud"
            else "reasoning_inner-monologue.md"
        )
    )

    return f"{reasoning}\n{tag_format}"


@lru_cache
def _load_mechanics(deps: PlayerDeps) -> str:
    """Load the mechanics for the given protocol."""
    if deps.protocol.role == "expert":
        return PromptCache.get_text(paths.prompts.joinpath("mechanics_expert.md"))

    if deps.protocol.role == "defuser":
        mechanics = PromptCache.get_text(
            paths.prompts.joinpath(
                "mechanics_defuser_realtime.md"
                if deps.protocol.communication_style == "async"
                else "mechanics_defuser.md"
            )
        )
        non_bomb_elements = PromptCache.get_text(
            paths.prompts.joinpath("mechanics_defuser_non-bomb-elements.md")
        )

        location = PromptCache.get_text(
            paths.prompts.joinpath(
                f"mechanics_defuser_{deps.capabilities.interaction_location_method}.md"
            )
        )
        if deps.capabilities.interaction_location_method == "coordinates":
            location = location.replace(
                "{IMAGE_WIDTH}", str(deps.capabilities.image_dimensions.width)
            ).replace("{IMAGE_HEIGHT}", str(deps.capabilities.image_dimensions.height))

        return f"{mechanics}\n{non_bomb_elements}\n{location}"

    raise NoPromptForProtocolError(deps.protocol, prompt_category="mechanics")


@lru_cache
def _load_commands(deps: PlayerDeps) -> str:
    """Load the commands for the given protocol."""
    commands = PromptCache.get_text(paths.prompts.joinpath("commands.md"))

    # load do nothing command
    do_nothing = PromptCache.get_text(paths.prompts.joinpath("commands_do_nothing.md"))
    commands = f"{commands}\n{do_nothing}"

    # load send message
    if deps.protocol.allow_message_output:
        send_message = PromptCache.get_text(paths.prompts.joinpath("commands_send_message.md"))
        commands = f"{commands}\n{send_message}"

    # if defuser, load interact game
    if deps.protocol.role == "defuser":
        interact_game = PromptCache.get_text(paths.prompts.joinpath("commands_interact_game.md"))
        location = PromptCache.get_text(
            paths.prompts.joinpath(
                f"commands_interact_game_{deps.capabilities.interaction_location_method}.md"
            )
        )
        if deps.capabilities.interaction_location_method == "coordinates":
            location = location.replace(
                "{IMAGE_WIDTH}", str(deps.capabilities.image_dimensions.width)
            ).replace("{IMAGE_HEIGHT}", str(deps.capabilities.image_dimensions.height))

        interact_game = f"{interact_game}\n{location}"
        commands = f"{commands}\n{interact_game}"

    return commands


@lru_cache
def _load_action_requirements(deps: PlayerDeps) -> str:
    """Load the action requirements for the given protocol."""
    action = PromptCache.get_text(paths.prompts.joinpath("requirements_action.md"))
    if deps.protocol.communication_style == "async":
        action_realtime = PromptCache.get_text(
            paths.prompts.joinpath(
                "requirements_action_realtime.md"
                if deps.protocol.communication_style == "async"
                else "requirements_action.md"
            )
        )
        action = f"{action}\n{action_realtime}"
    if deps.capabilities.interaction_location_method == "set-of-marks":
        action_location = PromptCache.get_text(
            paths.prompts.joinpath("requirements_action_set-of-marks.md")
        )
        action = f"{action}\n{action_location}"
    return action


@lru_cache
def _load_observation_requirements(deps: PlayerDeps) -> str:
    """Load the observation requirements for the given protocol."""
    observation = PromptCache.get_text(paths.prompts.joinpath("requirements_observation.md"))
    # optionally load set-of-marks observation details
    if deps.capabilities.interaction_location_method == "set-of-marks":
        observation_location = PromptCache.get_text(
            paths.prompts.joinpath("requirements_observation_set-of-marks.md")
        )
        observation = f"{observation}\n{observation_location}"
    return observation


@lru_cache
def load_formatting_requirements(deps: PlayerDeps) -> str:
    """Load the formatting requirements for the given protocol."""
    if deps.capabilities.structured_output_mode is not None:
        return PromptCache.get_text(
            paths.prompts.joinpath("requirements_formatting_structured-output.md")
        )
    return PromptCache.get_text(paths.prompts.joinpath("requirements_formatting.md"))


@lru_cache
def _load_requirements(deps: PlayerDeps) -> str:
    """Load the requirements for the given protocol."""
    requirements = PromptCache.get_text(paths.prompts.joinpath("requirements.md"))

    # if defuser, load action + observation
    if deps.protocol.role == "defuser":
        action = _load_action_requirements(deps)

        observation = _load_observation_requirements(deps)

        requirements = f"{requirements}\n{action}\n{observation}"

    # Load communication
    if deps.protocol.allow_message_output:
        communication = PromptCache.get_text(
            paths.prompts.joinpath(f"requirements_communication_{deps.protocol.role}.md")
        )
        # optionally load set-of-marks communication details for defuser player
        if (
            deps.protocol.role == "defuser"
            and deps.capabilities.interaction_location_method == "set-of-marks"
        ):
            communication_location = PromptCache.get_text(
                paths.prompts.joinpath("requirements_communication_defuser_set-of-marks.md")
            )
            communication = f"{communication}\n{communication_location}"

        requirements = f"{requirements}\n{communication}"

    # Load completion
    completion = PromptCache.get_text(
        paths.prompts.joinpath(f"requirements_completion_{deps.protocol.role}.md")
    )
    requirements = f"{requirements}\n{completion}"

    formatting = load_formatting_requirements(deps)

    requirements = f"{requirements}\n{formatting}"
    return requirements


@lru_cache
def load_instructions(deps: PlayerDeps) -> str:
    """Load the instructions for the given player."""
    scenario = _load_scenario(deps)
    role = _load_role(deps)
    reasoning = _load_reasoning(deps)
    mechanics = _load_mechanics(deps)
    commands: str = _load_commands(deps)
    requirements = _load_requirements(deps)

    instructions = f"{scenario}\n{role}\n{reasoning}\n{mechanics}\n{commands}\n{requirements}"
    instructions = instructions.strip()
    return instructions


PROMPTED_OUTPUT_TEMPLATE = dedent(
    """
    Always respond with a JSON object that's compatible with this schema:

    {schema}

    """
)


def create_output_schema_for_instructions[OutputT](structured_output_type: type[OutputT]) -> str:
    """Manually create the schema for PromptedOutput based on the current deps."""
    output_schema = OutputSchema[OutputT].build(PromptedOutput(structured_output_type))
    assert output_schema.object_def is not None

    instruction_suffix = PromptedOutputSchema.build_instructions(
        PROMPTED_OUTPUT_TEMPLATE, output_schema.object_def
    )
    return instruction_suffix


def load_instructions_from_deps(ctx: RunContext[PlayerDeps]) -> str:
    """Load instructions for the given player dynamically for the current agent."""
    instructions = load_instructions(ctx.deps)

    if ctx.deps.should_manually_add_schema_in_instructions:
        schema = create_output_schema_for_instructions(ctx.deps.structured_output_type)
        instructions = f"{instructions}\n\n{schema}"
    return instructions
