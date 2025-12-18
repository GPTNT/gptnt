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
    return PromptCache.get_text(paths.prompts.joinpath("scenario.md"))


@lru_cache
def _load_role(protocol: PlayerProtocol) -> str:
    """Load the role for the given protocol."""
    if protocol.role == "expert" and not protocol.is_playing_alone:
        return PromptCache.get_text(paths.prompts.joinpath("roles_expert.md"))
    if protocol.role == "defuser" and not protocol.is_playing_alone:
        return PromptCache.get_text(paths.prompts.joinpath("roles_defuser.md"))
    if protocol.role == "defuser" and protocol.is_playing_alone:
        path = (
            "roles_defuser_solo-player.md"
            if protocol.include_manual
            else "roles_defuser_solo-defuser.md"
        )

        return PromptCache.get_text(paths.prompts.joinpath(path))

    raise NoPromptForProtocolError(protocol, prompt_category="role")


@lru_cache
def _load_mechanics(protocol: PlayerProtocol) -> str:
    """Load the mechanics for the given protocol."""
    if protocol.role == "expert":
        return PromptCache.get_text(paths.prompts.joinpath("mechanics_expert.md"))

    if protocol.role == "defuser":
        mechanics = PromptCache.get_text(
            paths.prompts.joinpath(
                "mechanics_defuser_realtime.md"
                if protocol.communication_style == "async"
                else "mechanics_defuser.md"
            )
        )
        non_bomb_elements = PromptCache.get_text(
            paths.prompts.joinpath("mechanics_defuser_non-bomb-elements.md")
        )

        location = PromptCache.get_text(
            paths.prompts.joinpath(f"mechanics_defuser_{protocol.interaction_location_method}.md")
        )
        if protocol.interaction_location_method == "coordinates":
            # TODO: retrieve image width and height from the player config
            location = location.replace("{IMAGE_WIDTH}", str(640)).replace(
                "{IMAGE_HEIGHT}", str(480)
            )

        return f"{mechanics}\n{non_bomb_elements}\n{location}"

    raise NoPromptForProtocolError(protocol, prompt_category="mechanics")


@lru_cache
def _load_commands(protocol: PlayerProtocol) -> str:
    """Load the commands for the given protocol."""
    commands = PromptCache.get_text(paths.prompts.joinpath("commands.md"))

    # load do nothing command
    do_nothing = PromptCache.get_text(paths.prompts.joinpath("commands_do_nothing.md"))
    commands = f"{commands}\n{do_nothing}"

    # load send message
    if protocol.allow_message_output:
        send_message = PromptCache.get_text(paths.prompts.joinpath("commands_send_message.md"))
        commands = f"{commands}\n{send_message}"

    # if defuser, load interact game
    if protocol.role == "defuser":
        interact_game = PromptCache.get_text(paths.prompts.joinpath("commands_interact_game.md"))
        location = PromptCache.get_text(
            paths.prompts.joinpath(
                f"commands_interact_game_{protocol.interaction_location_method}.md"
            )
        )
        if protocol.interaction_location_method == "coordinates":
            # TODO: retrieve image width and height from the player config
            location = location.replace("{IMAGE_WIDTH}", str(640)).replace(
                "{IMAGE_HEIGHT}", str(480)
            )
        interact_game = f"{interact_game}\n{location}"
        commands = f"{commands}\n{interact_game}"

    return commands


def _load_thoughts(protocol: PlayerProtocol) -> str:
    """Load the thoughts for the given protocol."""
    if not protocol.allow_thoughts_output:
        logger.debug("Thoughts are not allowed for this player", protocol=protocol)
        return ""

    thoughts = PromptCache.get_text(paths.prompts.joinpath("thoughts.md"))

    if protocol.role == "expert":
        # if expert, load thoughts for expert
        thoughts = f"{thoughts}\n{PromptCache.get_text(paths.prompts.joinpath('thoughts_format_expert.md'))}"

    if protocol.role == "defuser":
        path = "thoughts_format_defuser{solo}.md".format(
            solo="_solo" if protocol.is_playing_alone else ""
        )
        thoughts = f"{thoughts}\n{PromptCache.get_text(paths.prompts.joinpath(path))}"
        thoughts_location = PromptCache.get_text(
            paths.prompts.joinpath(
                f"thoughts_format_defuser_{protocol.interaction_location_method}.md"
            )
        )
        thoughts = f"{thoughts}\n{thoughts_location}"

    return thoughts


@lru_cache
def _load_action_requirements(protocol: PlayerProtocol) -> str:
    """Load the action requirements for the given protocol."""
    action = PromptCache.get_text(paths.prompts.joinpath("requirements_action.md"))
    if protocol.communication_style == "async":
        action_realtime = PromptCache.get_text(
            paths.prompts.joinpath(
                "requirements_action_realtime.md"
                if protocol.communication_style == "async"
                else "requirements_action.md"
            )
        )
        action = f"{action}\n{action_realtime}"
    if protocol.interaction_location_method == "set-of-marks":
        action_location = PromptCache.get_text(
            paths.prompts.joinpath("requirements_action_set-of-marks.md")
        )
        action = f"{action}\n{action_location}"
    return action


@lru_cache
def _load_observation_requirements(protocol: PlayerProtocol) -> str:
    """Load the observation requirements for the given protocol."""
    observation = PromptCache.get_text(paths.prompts.joinpath("requirements_observation.md"))
    # optionally load set-of-marks observation details
    if protocol.interaction_location_method == "set-of-marks":
        observation_location = PromptCache.get_text(
            paths.prompts.joinpath("requirements_observation_set-of-marks.md")
        )
        observation = f"{observation}\n{observation_location}"
    return observation


@lru_cache
def _load_requirements(protocol: PlayerProtocol) -> str:
    """Load the requirements for the given protocol."""
    requirements = PromptCache.get_text(paths.prompts.joinpath("requirements.md"))

    # if defuser, load action + observation
    if protocol.role == "defuser":
        action = _load_action_requirements(protocol)

        observation = _load_observation_requirements(protocol)

        requirements = f"{requirements}\n{action}\n{observation}"

    # Load communication
    if protocol.allow_message_output:
        communication = PromptCache.get_text(
            paths.prompts.joinpath(f"requirements_communication_{protocol.role}.md")
        )
        # optionally load thoughts communication details
        if protocol.allow_thoughts_output:
            communication_thoughts = PromptCache.get_text(
                paths.prompts.joinpath(f"requirements_communication_{protocol.role}_thoughts.md")
            )
            communication = f"{communication}\n{communication_thoughts}"
        # optionally load set-of-marks communication details for defuser player
        if protocol.role == "defuser" and protocol.interaction_location_method == "set-of-marks":
            communication_location = PromptCache.get_text(
                paths.prompts.joinpath("requirements_communication_defuser_set-of-marks.md")
            )
            communication = f"{communication}\n{communication_location}"

        requirements = f"{requirements}\n{communication}"

    # Load completion
    completion = PromptCache.get_text(
        paths.prompts.joinpath(f"requirements_completion_{protocol.role}.md")
    )
    requirements = f"{requirements}\n{completion}"

    formatting = PromptCache.get_text(paths.prompts.joinpath("requirements_formatting.md"))
    requirements = f"{requirements}\n{formatting}"
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

    instructions = f"{scenario}\n{role}\n{mechanics}\n{commands}\n{thoughts}\n{requirements}"
    instructions = instructions.strip()
    return instructions


def load_instructions_from_deps(ctx: RunContext[PlayerDeps]) -> str:
    """Load instructions for the given player dynamically for the current agent."""
    return load_instructions(ctx.deps.protocol)
