from typing import Union, cast

from pydantic import BaseModel
from pydantic_ai import ModelProfile, NativeOutput, PromptedOutput, RunContext, ToolOutput
from pydantic_ai.output import OutputSpec

from gptnt.core.players.actions import (
    DoNothingAction,
    InteractGameAction,
    LotteryGameAction,
    MagicGameAction,
    PlayerOutputType,
    SendMessageAction,
)
from gptnt.core.prompts.instructions import load_instructions
from gptnt.core.prompts.output_schema import (
    PROMPTED_OUTPUT_TEMPLATE,
    create_output_schema_for_instructions,
)
from gptnt.core.specification import PlayerCapabilities, PlayerProtocol

_default_template = ModelProfile().prompted_output_template


class PlayerDeps(BaseModel, frozen=True):
    """Dependencies for the AI player (as in PydanticAI)."""

    capabilities: PlayerCapabilities
    protocol: PlayerProtocol

    @property
    def output_type(self) -> OutputSpec[PlayerOutputType] | type[str]:
        """The output type for the player, determining the schema/structure if needed."""
        if self.capabilities.structured_output_mode is not None:
            match self.capabilities.structured_output_mode:
                case "native":
                    return NativeOutput(self.structured_output_type)
                case "tool":
                    return ToolOutput(self.structured_output_type)
                case "prompted":
                    return PromptedOutput(self.structured_output_type)
        return str

    @property
    def structured_output_type(self) -> type[PlayerOutputType]:
        """The output type for the player.

        This is used to determine what the agent can output.

        Note that at the end, we also patch the name so that it can be used by various tool
        functions because for some reason, this was not working properly.
        """
        output: list[type[PlayerOutputType]] = []
        output.append(DoNothingAction)

        if not self.protocol.is_playing_alone:
            output.append(SendMessageAction)

        if self.protocol.role == "defuser":
            output.append(InteractGameAction[self.capabilities.interact_location_type])

        if self.protocol.allow_magic_actions:
            output.append(MagicGameAction)

        if self.protocol.allow_lottery_actions:
            output.append(LotteryGameAction)

        clean_output: list[type[PlayerOutputType]] = []
        for output_type in output:
            # Remove the brackets from the output type name
            output_type.__name__ = output_type.__name__.replace("[", "").replace("]", "")
            output_type.__qualname__ = output_type.__qualname__.replace("[", "").replace("]", "")
            clean_output.append(output_type)

        return cast("type[PlayerOutputType]", Union[tuple(clean_output)])  # noqa: UP007

    @property
    def should_manually_add_schema_in_instructions(self) -> bool:
        """Whether we should manually include the output schema in the instructions.

        If we are using prompted, then the schema is automatically included and therefore we should
        not include it again. Otherwise, we depend on the capability flag.
        """
        return (
            self.capabilities.structured_output_mode != "prompted"
            and self.capabilities.include_schema_in_instructions
        )

    @property
    def schema_template(self) -> str:
        """The schema template to use for the output schema in instructions.

        If we are using structured outputs, then we use the prompted output template from Pydantic-
        AI's PromptedOutput mode. Otherwise, we use our custom one, which is very similar, but just
        doesn't have the last line.
        """
        if self.capabilities.structured_output_mode is None:
            return PROMPTED_OUTPUT_TEMPLATE

        return _default_template


def load_instructions_from_deps(ctx: RunContext[PlayerDeps]) -> str:
    """Load instructions for the given player dynamically for the current agent."""
    instructions = load_instructions(ctx.deps.protocol, ctx.deps.capabilities)

    if ctx.deps.should_manually_add_schema_in_instructions:
        schema = create_output_schema_for_instructions(
            ctx.deps.structured_output_type, template=ctx.deps.schema_template
        )
        instructions = f"{instructions}\n\n{schema}"
    return instructions
