from collections.abc import Callable, Iterator
from typing import Literal, NamedTuple

type PairingType = Literal[
    "with_best_defuser", "with_best_expert", "with_self", "no_expert", "pairwise"
]


class Pairing(NamedTuple):
    """Pairing for a game."""

    defuser: str
    expert: str | None


class PairingGenerator:
    """Generate all the possible pairings for a game.

    This covers all the different types of experiments we are going to run. Note that if you want
    to generate `with_best_defuser` or `with_best_expert`, then you need to give the `best_model`.
    """

    def __init__(
        self, *, pairing_type: PairingType, all_players: list[str], best_model: str | None = None
    ) -> None:
        if "with_best" in pairing_type and best_model is None:
            raise ValueError(
                "`best_model` must be provided when `pairing_type` contains `with_best`"
            )

        self.pairing_type: PairingType = pairing_type
        self.best_model = best_model
        self.all_players = all_players

    def generate(self) -> Iterator[Pairing]:
        """Generate all the pairings."""
        switcher: dict[PairingType, Callable[[list[str]], Iterator[Pairing]]] = {
            "with_best_defuser": self._generate_with_best_defuser,
            "with_best_expert": self._generate_with_best_expert,
            "with_self": self._generate_with_self,
            "no_expert": self._generate_no_expert,
            "pairwise": self._generate_pairwise,
        }
        yield from switcher[self.pairing_type](self.all_players)

    def _generate_with_best_defuser(self, all_players: list[str]) -> Iterator[Pairing]:
        """Generate pairings with the best model."""
        assert self.best_model is not None

        if self.best_model in all_players:
            all_players = [player for player in all_players if player != self.best_model]

        for player in all_players:
            yield Pairing(defuser=self.best_model, expert=player)

    def _generate_with_best_expert(self, all_players: list[str]) -> Iterator[Pairing]:
        """Generate pairings with the best model."""
        assert self.best_model is not None

        if self.best_model in all_players:
            all_players = [player for player in all_players if player != self.best_model]

        for player in all_players:
            yield Pairing(defuser=player, expert=self.best_model)

    def _generate_with_self(self, all_players: list[str]) -> Iterator[Pairing]:
        """Generate pairings with self."""
        yield from (Pairing(defuser=player, expert=player) for player in all_players)

    def _generate_no_expert(self, all_players: list[str]) -> Iterator[Pairing]:
        """Generate pairings with no partner, therefore only defuser given."""
        yield from (Pairing(defuser=player, expert=None) for player in all_players)

    def _generate_pairwise(self, all_players: list[str]) -> Iterator[Pairing]:
        """Generate pairwise pairings."""
        for player in all_players:
            for partner in all_players:
                yield Pairing(defuser=player, expert=partner)
