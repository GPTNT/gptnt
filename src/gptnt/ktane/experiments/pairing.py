from collections.abc import Callable, Iterator
from typing import Literal, override

from pydantic import BaseModel

type PairingType = Literal["with_best", "with_self", "no_partner", "pairwise"]


class Pairing(BaseModel):
    """Pairing for a game."""

    defuser: str
    expert: str | None
    pairing_type: PairingType

    @override
    def __str__(self) -> str:
        output = f"{self.defuser}_{self.expert}_{self.pairing_type}"
        return output

    @override
    def __hash__(self) -> int:
        return hash((self.defuser, self.expert, self.pairing_type))


class PairingGenerator:
    """Generate all the possible pairings for a game.

    This covers all the different types of experiments we are going to run. Note that if you want
    to generate `with_best`, then you need to give the `best_model`.
    """

    def __init__(
        self, *, pairing_type: PairingType, all_players: list[str], best_model: str | None = None
    ) -> None:
        if pairing_type == "with_best" and best_model is None:
            raise ValueError("`best_model` must be provided when `pairing_type=with_best`")

        self.pairing_type: PairingType = pairing_type
        self.best_model = best_model
        self.all_players = all_players

    def generate(self) -> Iterator[Pairing]:
        """Generate all the pairings."""
        switcher: dict[PairingType, Callable[[list[str]], Iterator[Pairing]]] = {
            "with_best": self._generate_with_best,
            "with_self": self._generate_with_self,
            "no_partner": self._generate_no_partner,
            "pairwise": self._generate_pairwise,
        }
        yield from switcher[self.pairing_type](self.all_players)

    def _generate_with_best(self, all_players: list[str]) -> Iterator[Pairing]:
        """Generate pairings with the best model."""
        assert self.best_model is not None

        if self.best_model in all_players:
            all_players = [player for player in all_players if player != self.best_model]

        for player in all_players:
            yield from (
                Pairing(defuser=player, expert=self.best_model, pairing_type=self.pairing_type),
                Pairing(defuser=self.best_model, expert=player, pairing_type=self.pairing_type),
            )

    def _generate_with_self(self, all_players: list[str]) -> Iterator[Pairing]:
        """Generate pairings with self."""
        yield from (
            Pairing(defuser=player, expert=player, pairing_type=self.pairing_type)
            for player in all_players
        )

    def _generate_no_partner(self, all_players: list[str]) -> Iterator[Pairing]:
        """Generate pairings with no partner, therefore only defuser given."""
        yield from (
            Pairing(defuser=player, expert=None, pairing_type=self.pairing_type)
            for player in all_players
        )

    def _generate_pairwise(self, all_players: list[str]) -> Iterator[Pairing]:
        """Generate pairwise pairings."""
        for player in all_players:
            for partner in all_players:
                yield Pairing(defuser=player, expert=partner, pairing_type=self.pairing_type)
