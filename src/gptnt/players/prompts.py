from functools import lru_cache
from typing import Literal

import structlog
from pydantic_ai import BinaryContent
from pydantic_ai.tools import RunContext

from gptnt.common.paths import Paths
from gptnt.common.prompt_cache import PromptCache
from gptnt.ktane.manual import MANUAL_NUM_PAGES, NEEDY_MODULE_PAGE_NUMS, KtaneManualPaths
from gptnt.ktane.state.bomb import BombState
from gptnt.players.spec import PlayerDeps, PlayerSpec

paths = Paths()

logger = structlog.get_logger()


ReflectionMessage = Literal["terminated-exploded", "truncated-exploded", "terminated-defused"]
"""Reflection messages for the player to use when reflecting on the bomb state."""


@lru_cache(maxsize=1)
def load_manual_as_prompt(
    *, num_pages: int = MANUAL_NUM_PAGES, skip_needy_modules: bool = True
) -> list[str | BinaryContent]:
    """Load the content for the manual."""
    logger.debug(f"Loading {num_pages} pages of the manual")
    manual_paths = KtaneManualPaths()

    manual = []
    for page_num in range(1, num_pages + 1):
        if skip_needy_modules and page_num in NEEDY_MODULE_PAGE_NUMS:
            # Skip the needy module pages
            continue

        # Load the text for the page first
        text = manual_paths.load_text(page_num)
        manual.append(text)

        # Load the image for the page afterwards
        image = manual_paths.load_image(page_num, kind="512")
        image = BinaryContent(image, media_type="image/png")
        manual.append(image)

    return manual


@lru_cache(maxsize=1)
def load_reflection_prompt() -> str:
    """Load the prompt for the given state."""
    return PromptCache.get_text(paths.prompts.joinpath("reflection.txt"))


def convert_bomb_state_to_reflection(bomb_state: BombState) -> ReflectionMessage | None:
    """Convert the bomb state to a reflection message."""
    final_message: ReflectionMessage | None = None
    if bomb_state.is_detonated is True:
        if bomb_state.timer_module.seconds_remaining <= 0:
            # bomb detonated because player ran out of time
            final_message = "terminated-exploded"
        else:
            # bomb detonated because player made too many mistakes
            final_message = "truncated-exploded"

    if bomb_state.is_solved is True:
        # player solved all modules on bomb
        final_message = "terminated-defused"

    if not final_message:
        logger.exception("No logic connecting bomb state to final message")

    return final_message


@lru_cache
def _load_scenario_for_spec(spec: PlayerSpec) -> str:
    """Load the scenario for the given player spec."""
    if spec.is_playing_alone:
        logger.debug("Loading scenario for solo")
        return PromptCache.get_text(paths.prompts.joinpath("scenario_solo.md"))

    logger.debug("Loading scenario for multiplayer")
    return PromptCache.get_text(paths.prompts.joinpath("scenario_multiplayer.md"))


@lru_cache
def _load_role_for_spec(spec: PlayerSpec) -> str:
    """Load the role for the given player spec."""
    if spec.role == "expert" and not spec.is_playing_alone:
        return PromptCache.get_text(paths.prompts.joinpath("roles_multiplayer_expert.md"))
    if spec.role == "defuser":
        path = "roles_solo_defuser.md" if spec.is_playing_alone else "roles_multiplayer_defuser.md"
        return PromptCache.get_text(paths.prompts.joinpath(path))

    raise ValueError(
        f"Invalid player spec: {spec}. The role is not valid for the given player spec."
    )


@lru_cache
def _load_mechanics_for_spec(spec: PlayerSpec) -> str:
    """Load the mechanics for the given player spec."""
    if spec.role == "expert":
        return PromptCache.get_text(paths.prompts.joinpath("mechanics_expert.md"))

    if spec.role == "defuser":
        path = (
            "mechanics_defuser_realtime.md"
            if spec.communication_style == "async"
            else "mechanics_defuser.md"
        )
        return PromptCache.get_text(paths.prompts.joinpath(path))

    raise ValueError(
        f"Invalid player spec: {spec}. No mechanics exist valid for the given player spec."
    )


@lru_cache
def _load_commands_for_spec(spec: PlayerSpec) -> str:
    """Load the commands for the given player spec."""
    commands = PromptCache.get_text(paths.prompts.joinpath("commands.md"))

    # load do nothing command
    do_nothing = PromptCache.get_text(paths.prompts.joinpath("commands_do_nothing.md"))
    commands = f"{commands}{do_nothing}"

    # load send message
    if spec.allow_message_output:
        send_message = PromptCache.get_text(paths.prompts.joinpath("commands_send_message.md"))
        commands = f"{commands}{send_message}"

    # if defuser, load interact game
    if spec.role == "defuser":
        interact_game = PromptCache.get_text(paths.prompts.joinpath("commands_interact_game.md"))
        commands = f"{commands}{interact_game}"

    return commands


def _load_thoughts_for_spec(spec: PlayerSpec) -> str:
    """Load the thoughts for the given player spec."""
    if not spec.allow_thoughts_output:
        logger.debug("Thoughts are not allowed for this player spec", spec=spec)
        return ""

    thoughts = PromptCache.get_text(paths.prompts.joinpath("thoughts.md"))

    if spec.role == "expert":
        # if expert, load thoughts for expert
        thoughts = f"{thoughts}{PromptCache.get_text(paths.prompts.joinpath('thoughts_format_expert.md'))}"

    if spec.role == "defuser":
        path = "thoughts_format_defuser{solo}.md".format(
            solo="_solo" if spec.is_playing_alone else ""
        )
        thoughts = f"{thoughts}{PromptCache.get_text(paths.prompts.joinpath(path))}"

    return thoughts


@lru_cache
def _load_requirements_for_spec(spec: PlayerSpec) -> str:
    """Load the requirements for the given player spec."""
    requirements = PromptCache.get_text(paths.prompts.joinpath("requirements.md"))

    # if defuser, load action + observation
    if spec.role == "defuser":
        action = PromptCache.get_text(paths.prompts.joinpath("requirements_action.md"))
        observation = PromptCache.get_text(paths.prompts.joinpath("requirements_observation.md"))
        requirements = f"{requirements}{action}{observation}"

    # Load communication
    if spec.allow_message_output:
        communication_path = "requirements_communication{role}{thoughts}.md".format(
            role=f"_{spec.role}", thoughts="_thoughts" if spec.allow_thoughts_output else ""
        )
        communication = PromptCache.get_text(paths.prompts.joinpath(communication_path))
        requirements = f"{requirements}{communication}"

    completion = PromptCache.get_text(
        paths.prompts.joinpath(f"requirements_completion_{spec.role}.md")
    )
    requirements = f"{requirements}{completion}"

    formatting = PromptCache.get_text(paths.prompts.joinpath("requirements_formatting.md"))
    requirements = f"{requirements}{formatting}"
    return requirements


@lru_cache
def load_instructions_for_spec(spec: PlayerSpec) -> str:
    """Load the instructions for the given player spec."""
    scenario = _load_scenario_for_spec(spec)
    role = _load_role_for_spec(spec)
    mechanics = _load_mechanics_for_spec(spec)
    commands = _load_commands_for_spec(spec)
    thoughts = _load_thoughts_for_spec(spec)
    requirements = _load_requirements_for_spec(spec)

    instructions = f"{scenario}{role}{mechanics}{commands}{thoughts}{requirements}"
    instructions = instructions.strip()
    return instructions


def load_instructions_deps(ctx: RunContext[PlayerDeps]) -> str:
    """Load instructions for the given player dynamically for the current agent."""
    return load_instructions_for_spec(ctx.deps.spec)
