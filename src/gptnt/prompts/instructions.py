from functools import lru_cache

import structlog
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
def _load_scenario(protocol: PlayerProtocol) -> str:
    """Load the scenario for the given protocol."""
    if protocol.is_playing_alone:
        logger.debug("Loading scenario for solo")
        return PromptCache.get_text(paths.prompts.joinpath("scenario_solo.md"))

    logger.debug("Loading scenario for multiplayer")
    return PromptCache.get_text(paths.prompts.joinpath("scenario_multiplayer.md"))


@lru_cache
def _load_role(protocol: PlayerProtocol) -> str:
    """Load the role for the given protocol."""
    if protocol.role == "expert" and not protocol.is_playing_alone:
        return PromptCache.get_text(paths.prompts.joinpath("roles_multiplayer_expert.md"))
    if protocol.role == "defuser":
        path = (
            "roles_solo_defuser.md"
            if protocol.is_playing_alone
            else "roles_multiplayer_defuser.md"
        )
        return PromptCache.get_text(paths.prompts.joinpath(path))

    raise NoPromptForProtocolError(protocol, prompt_category="role")


@lru_cache
def _load_mechanics(protocol: PlayerProtocol) -> str:
    """Load the mechanics for the given protocol."""
    if protocol.role == "expert":
        return PromptCache.get_text(paths.prompts.joinpath("mechanics_expert.md"))

    if protocol.role == "defuser":
        path = (
            "mechanics_defuser_realtime.md"
            if protocol.communication_style == "async"
            else "mechanics_defuser.md"
        )
        return PromptCache.get_text(paths.prompts.joinpath(path))

    raise NoPromptForProtocolError(protocol, prompt_category="mechanics")


@lru_cache
def _load_commands(protocol: PlayerProtocol) -> str:
    """Load the commands for the given protocol."""
    commands = PromptCache.get_text(paths.prompts.joinpath("commands.md"))

    # load do nothing command
    do_nothing = PromptCache.get_text(paths.prompts.joinpath("commands_do_nothing.md"))
    commands = f"{commands}{do_nothing}"

    # load send message
    if protocol.allow_message_output:
        send_message = PromptCache.get_text(paths.prompts.joinpath("commands_send_message.md"))
        commands = f"{commands}{send_message}"

    # if defuser, load interact game
    if protocol.role == "defuser":
        interact_game = PromptCache.get_text(paths.prompts.joinpath("commands_interact_game.md"))
        commands = f"{commands}{interact_game}"

    return commands


def _load_thoughts(protocol: PlayerProtocol) -> str:
    """Load the thoughts for the given protocol."""
    if not protocol.allow_thoughts_output:
        logger.debug("Thoughts are not allowed for this player", protocol=protocol)
        return ""

    thoughts = PromptCache.get_text(paths.prompts.joinpath("thoughts.md"))

    if protocol.role == "expert":
        # if expert, load thoughts for expert
        thoughts = f"{thoughts}{PromptCache.get_text(paths.prompts.joinpath('thoughts_format_expert.md'))}"

    if protocol.role == "defuser":
        path = "thoughts_format_defuser{solo}.md".format(
            solo="_solo" if protocol.is_playing_alone else ""
        )
        thoughts = f"{thoughts}{PromptCache.get_text(paths.prompts.joinpath(path))}"

    return thoughts


@lru_cache
def _load_requirements(protocol: PlayerProtocol) -> str:
    """Load the requirements for the given protocol."""
    requirements = PromptCache.get_text(paths.prompts.joinpath("requirements.md"))

    # if defuser, load action + observation
    if protocol.role == "defuser":
        action = PromptCache.get_text(paths.prompts.joinpath("requirements_action.md"))
        observation = PromptCache.get_text(paths.prompts.joinpath("requirements_observation.md"))
        requirements = f"{requirements}{action}{observation}"

    # Load communication
    if protocol.allow_message_output:
        communication_path = "requirements_communication{role}{thoughts}.md".format(
            role=f"_{protocol.role}",
            thoughts="_thoughts" if protocol.allow_thoughts_output else "",
        )
        communication = PromptCache.get_text(paths.prompts.joinpath(communication_path))
        requirements = f"{requirements}{communication}"

    completion = PromptCache.get_text(
        paths.prompts.joinpath(f"requirements_completion_{protocol.role}.md")
    )
    requirements = f"{requirements}{completion}"

    formatting = PromptCache.get_text(paths.prompts.joinpath("requirements_formatting.md"))
    requirements = f"{requirements}{formatting}"
    return requirements


@lru_cache
def load_instructions(protocol: PlayerProtocol) -> str:
    """Load the instructions for the given protocol."""
    scenario = _load_scenario(protocol)
    role = _load_role(protocol)
    mechanics = _load_mechanics(protocol)
    commands = _load_commands(protocol)
    thoughts = _load_thoughts(protocol)
    requirements = _load_requirements(protocol)

    instructions = f"{scenario}{role}{mechanics}{commands}{thoughts}{requirements}"
    instructions = instructions.strip()
    return instructions


def load_instructions_from_deps(ctx: RunContext[PlayerDeps]) -> str:
    """Load instructions for the given player dynamically for the current agent."""
    return load_instructions(ctx.deps.protocol)
