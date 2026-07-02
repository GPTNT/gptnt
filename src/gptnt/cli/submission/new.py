from pathlib import Path
from typing import Annotated

from cyclopts import Parameter

from gptnt.cli.submission._interactive import build_interactive_submission
from gptnt.cli.submission._statics import build_statics_submission

_DEFAULT_INTO = Path("submissions")


def build_submission(
    outputs_dir: Path,
    *,
    suite: Annotated[
        str | None, Parameter(help="Suite config name for an interactive submission.")
    ] = None,
    static_task: Annotated[
        str | None, Parameter(help="Statics task name for a statics submission.")
    ] = None,
    into: Annotated[
        Path, Parameter(help="Root directory to write the bundle under.")
    ] = _DEFAULT_INTO,
) -> None:
    """Build a submission bundle from a local experiment outputs directory.

    Exactly one of `--suite` (interactive KTANE results) or `--static-task` (a HuggingFace no-game
    evaluation) selects the source path. With neither, the interactive path is used and the suite
    is inferred when the outputs contain exactly one.
    """
    if static_task is not None and suite is not None:
        raise ValueError("Pass only one of --suite or --static-task.")

    if static_task is not None:
        _ = build_statics_submission(outputs_dir, static_task, into)
        return

    _ = build_interactive_submission(outputs_dir, suite, into)
