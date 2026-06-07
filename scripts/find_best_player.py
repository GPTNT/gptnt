from collections import Counter

import wandb
from rich import box
from rich.console import Console
from rich.table import Table
from structlog import get_logger

from gptnt.core.common.logger import configure_logging

_logger = get_logger()

configure_logging()
console = Console()


def create_leaderboard(counter: Counter, title: str) -> Table:
    """Create a simple leaderboard table."""
    table = Table(title=title, show_header=True, box=box.ROUNDED)
    table.add_column("Player", style="cyan")
    table.add_column("Wins", justify="right", style="green")

    for player, wins in counter.most_common():
        table.add_row(player, str(wins))

    return table


def create_pairwise_table(pair_counter: Counter) -> Table:
    """Create a pairwise matrix table."""
    # Get all unique players
    all_players = set()
    for defuser, expert in pair_counter:
        all_players.add(defuser)
        all_players.add(expert)
    all_players = sorted(all_players)

    table = Table(
        title="Pairwise Wins Matrix (Defuser vs Expert)",
        show_header=True,
        box=box.ROUNDED,
        header_style="cyan",
        caption="(defuser, expert) == (row, column)",
    )

    table.add_column("", style="cyan", width=12)

    for expert in all_players:
        table.add_column(expert, justify="center", width=10)

    for defuser in all_players:
        row = [defuser]
        for expert in all_players:
            count = pair_counter.get((defuser, expert), 0)
            row.append(str(count))
        table.add_row(*row)

    return table


def find_best_e1_player() -> None:
    """Get the game IDs for the games that were solved."""
    wandb_runs = wandb.Api().runs(
        path="gptnt/for-real",
        filters={
            "$and": [
                {"state": "finished"},
                {"summary_metrics.hard_crash": False},
                {"summary_metrics.is_solved": True},
                {"tags": {"$nin": ["old"]}},
                # e1 == single module and thinking allowed
                # {"config.communication_style": "sync"},
                {"config.condition": "single_module"},
                {"config.thinking_framework": "react"},
                {"config.is_playing_alone": False},
            ]
        },
    )

    defuser_wins = []
    expert_wins = []
    winning_pairs = []

    _logger.info("Checking for existing runs on wandb. This might take a while...")
    _logger.info("Found existing runs on wandb", runs=len(wandb_runs))

    for run in wandb_runs:
        defuser_wins.append(run.config["defuser_name"])
        expert_wins.append(run.config["expert_name"])
        winning_pairs.append((run.config["defuser_name"], run.config["expert_name"]))

    defuser_counter = Counter(defuser_wins)
    expert_counter = Counter(expert_wins)
    pair_counter = Counter(winning_pairs)

    # Display leaderboards
    console.print(create_leaderboard(defuser_counter, "As Defuser"))
    console.print()
    console.print(create_leaderboard(expert_counter, "As Expert"))
    console.print()

    # Display pairwise matrix
    console.print(create_pairwise_table(pair_counter))


if __name__ == "__main__":
    find_best_e1_player()
