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

    formatting = PromptCache.get_text(paths.prompts.joinpath("requirements_formatting.md"))
    requirements = f"{requirements}\n{formatting}"
    return requirements


@lru_cache
def load_instructions(deps: PlayerDeps) -> str:
    """Load the instructions for the given player."""
    scenario = _load_scenario(deps)
    role = _load_role(deps)
    mechanics = _load_mechanics(deps)
    commands = _load_commands(deps)
    requirements = _load_requirements(deps)

    instructions = f"{scenario}\n{role}\n{mechanics}\n{commands}\n{requirements}"
    instructions = instructions.strip()
    return instructions


def load_instructions_from_deps(ctx: RunContext[PlayerDeps]) -> str:
    """Load instructions for the given player dynamically for the current agent."""
    return load_instructions(ctx.deps)
