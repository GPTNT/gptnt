from gptnt.experiments.pairing import PairingGenerator

ALL_PLAYERS = frozenset(("gpt4o", "claude37", "gemini"))


def test_pairing_with_self_works() -> None:
    """Test that pairing with self works."""
    generator = PairingGenerator(pairing_type="with_self", all_players=ALL_PLAYERS)
    pairings = list(generator.generate())
    assert len(pairings) == len(ALL_PLAYERS), "Should generate one pairing per player"
    for pairing in pairings:
        assert pairing.defuser == pairing.expert, "Defuser and expert should be the same"
        assert pairing.defuser in ALL_PLAYERS, "Defuser should be in all players"


def test_pairing_with_best_defuser_works() -> None:
    """Test that pairing with best works."""
    generator = PairingGenerator(
        pairing_type="with_best_defuser", all_players=ALL_PLAYERS, best_model="gemini"
    )
    pairings = list(generator.generate())

    assert len(pairings) == (len(ALL_PLAYERS) - 1), (
        "Should generate two pairings per player except the best"
    )

    for pairing in pairings:
        assert pairing.defuser != pairing.expert, "Defuser and expert should be different"
        assert pairing.expert == "gemini" or pairing.defuser == "gemini", (
            "One of them should be the best model"
        )


def test_pairing_with_best_expert_works() -> None:
    """Test that pairing with best works."""
    generator = PairingGenerator(
        pairing_type="with_best_expert", all_players=ALL_PLAYERS, best_model="gemini"
    )
    pairings = list(generator.generate())

    assert len(pairings) == (len(ALL_PLAYERS) - 1), (
        "Should generate two pairings per player except the best"
    )

    for pairing in pairings:
        assert pairing.defuser != pairing.expert, "Defuser and expert should be different"
        assert pairing.expert == "gemini" or pairing.defuser == "gemini", (
            "One of them should be the best model"
        )


def test_pairing_no_partner_works() -> None:
    """Test that pairing with no partner works."""
    generator = PairingGenerator(pairing_type="no_partner", all_players=ALL_PLAYERS)
    pairings = list(generator.generate())
    assert len(pairings) == len(ALL_PLAYERS), "Should generate one pairing per player"
    for pairing in pairings:
        assert pairing.expert is None, "Expert should be None"
        assert pairing.defuser != pairing.expert, "Defuser and expert should be different"
        assert pairing.defuser in ALL_PLAYERS, "Defuser should be in all players"


def test_pairing_pairwise_works() -> None:
    """Test that pairing pairwise works."""
    generator = PairingGenerator(pairing_type="pairwise", all_players=ALL_PLAYERS)
    pairings = list(generator.generate())
    assert len(pairings) == len(ALL_PLAYERS) * len(ALL_PLAYERS), (
        "Should generate pairing per player including self"
    )
    for pairing in pairings:
        assert pairing.defuser in ALL_PLAYERS, "Defuser should be in all players"
        assert pairing.expert in ALL_PLAYERS, "Expert should be in all players"
