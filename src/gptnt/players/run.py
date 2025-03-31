import abc


class RunPlayerMixin(abc.ABC):
    """Mixin to interface running the player in its loop."""

    @abc.abstractmethod
    async def run(self) -> None:
        """Run the player."""
        raise NotImplementedError
