from functools import lru_cache

import structlog

from gptnt.common.paths import Paths
from gptnt.players.specification import PlayerCapabilities, PlayerProtocol
from gptnt.prompts.prompt_cache import PromptCache

paths = Paths()

logger = structlog.get_logger()


@lru_cache
def _load_scenario(protocol: PlayerProtocol) -> str:
    """Load the scenario for the protocol."""
    if protocol.is_playing_alone:
        logger.debug("Loading scenario for solo")
        return PromptCache.get_text(paths.prompts.joinpath("scenario_solo.md"))

    logger.debug("Loading scenario for multiplayer")
    return PromptCache.get_text(paths.prompts.joinpath("scenario.md"))


@lru_cache
def _load_role(protocol: PlayerProtocol) -> str:
    """Load the role for the protocol."""
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

    raise ValueError(f"No role prompt found for protocol: {protocol}")


@lru_cache
def _load_reasoning(capabilities: PlayerCapabilities) -> str:
    """Load the self-contained prompt for the configured reasoning mode."""
    return PromptCache.get_text(
        paths.prompts.joinpath(f"reasoning_{capabilities.thinking_method}.md")
    )


@lru_cache
def _load_mechanics(protocol: PlayerProtocol, capabilities: PlayerCapabilities) -> str:
    """Load the mechanics for the protocol."""
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
            paths.prompts.joinpath(
                f"mechanics_defuser_{capabilities.interaction_location_method}.md"
            )
        )
        if capabilities.interaction_location_method == "coordinates":
            location = location.replace(
                "{IMAGE_WIDTH}", str(capabilities.image_dimensions.width)
            ).replace("{IMAGE_HEIGHT}", str(capabilities.image_dimensions.height))

        return f"{mechanics}\n{non_bomb_elements}\n{location}"

    raise ValueError(f"No mechanics prompt found for protocol: {protocol}")


@lru_cache
def _load_commands(protocol: PlayerProtocol, capabilities: PlayerCapabilities) -> str:
    """Load the commands for the protocol."""
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
                f"commands_interact_game_{capabilities.interaction_location_method}.md"
            )
        )
        if capabilities.interaction_location_method == "coordinates":
            location = location.replace(
                "{IMAGE_WIDTH}", str(capabilities.image_dimensions.width)
            ).replace("{IMAGE_HEIGHT}", str(capabilities.image_dimensions.height))

        interact_game = f"{interact_game}\n{location}"
        commands = f"{commands}\n{interact_game}"

    # Command fragments own only their JSON payload. The selected output mode adds the envelope:
    # non-structured responses use ReAct action tags, while structured modes use bare JSON.
    if capabilities.structured_output_mode is None:
        commands = commands.replace("`{", "`<action>{").replace("}`", "}</action>`")

    return commands


@lru_cache
def _load_action_requirements(protocol: PlayerProtocol, capabilities: PlayerCapabilities) -> str:
    """Load the action requirements for the protocol."""
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
    if capabilities.interaction_location_method == "set-of-marks":
        action_location = PromptCache.get_text(
            paths.prompts.joinpath("requirements_action_set-of-marks.md")
        )
        action = f"{action}\n{action_location}"
    return action


@lru_cache
def _load_observation_requirements(capabilities: PlayerCapabilities) -> str:
    """Load the observation requirements for the protocol."""
    observation = PromptCache.get_text(paths.prompts.joinpath("requirements_observation.md"))
    # optionally load set-of-marks observation details
    if capabilities.interaction_location_method == "set-of-marks":
        observation_location = PromptCache.get_text(
            paths.prompts.joinpath("requirements_observation_set-of-marks.md")
        )
        observation = f"{observation}\n{observation_location}"
    return observation


@lru_cache
def load_formatting_requirements(capabilities: PlayerCapabilities) -> str:
    """Load the formatting requirements for the protocol."""
    if capabilities.structured_output_mode is not None:
        return PromptCache.get_text(
            paths.prompts.joinpath("requirements_formatting_structured-output.md")
        )
    return PromptCache.get_text(paths.prompts.joinpath("requirements_formatting.md"))


@lru_cache
def _load_requirements(protocol: PlayerProtocol, capabilities: PlayerCapabilities) -> str:
    """Load the requirements for the protocol."""
    requirements = PromptCache.get_text(paths.prompts.joinpath("requirements.md"))

    # if defuser, load action + observation
    if protocol.role == "defuser":
        action = _load_action_requirements(protocol, capabilities)

        observation = _load_observation_requirements(capabilities)

        requirements = f"{requirements}\n{action}\n{observation}"

    # Load communication
    if protocol.allow_message_output:
        communication = PromptCache.get_text(
            paths.prompts.joinpath(f"requirements_communication_{protocol.role}.md")
        )
        # optionally load set-of-marks communication details for defuser player
        if (
            protocol.role == "defuser"
            and capabilities.interaction_location_method == "set-of-marks"
        ):
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

    formatting = load_formatting_requirements(capabilities)

    requirements = f"{requirements}\n{formatting}"
    return requirements


@lru_cache
def load_instructions(protocol: PlayerProtocol, capabilities: PlayerCapabilities) -> str:
    """Load the instructions for the player."""
    scenario = _load_scenario(protocol)
    role = _load_role(protocol)
    reasoning = _load_reasoning(capabilities)
    mechanics = _load_mechanics(protocol, capabilities)
    commands = _load_commands(protocol, capabilities)
    requirements = _load_requirements(protocol, capabilities)

    instructions = f"{scenario}\n{role}\n{reasoning}\n{mechanics}\n{commands}\n{requirements}"
    instructions = instructions.strip()
    return instructions
