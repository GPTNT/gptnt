"""Guard the CLI's fast `--help`: command modules must defer heavy imports.

Every `gptnt` subcommand registers its function at the top of an assembly module
(`gptnt.cli.__main__` / `gptnt.interactive.__main__`), so importing those modules runs
every command module's top level. To keep `gptnt --help` fast, each command must import its
heavy dependencies *inside* its function body, not at module top level. This test fails if a new
or changed command pulls one of those heavy deps at import time.
"""

import subprocess
import sys

import pytest

# Heavy third-party deps that no command may import at module top level — they must be imported
# inside the command function body instead (see any module under packages/**/cli/).
#
# httpx / logfire / psutil / pydantic_ai are intentionally NOT listed: they load unavoidably via
# the shared option-type aliases (`gptnt.core.config` -> pydantic -> logfire) and the structlog
# setup, not from any single command, so they are part of the fixed baseline rather than a leak.
FORBIDDEN_AT_IMPORT = (
    "polars",
    "duckdb",
    "wandb",
    "weave",
    "hydra",
    "datasets",
    "torch",
    "transformers",
    "coredis",
    "faststream",
    "fastapi",
)

ASSEMBLY_MODULES = ("gptnt.cli.__main__", "gptnt.interactive.__main__")


@pytest.mark.parametrize("assembly_module", ASSEMBLY_MODULES)
def test_cli_assembly_defers_heavy_imports(assembly_module: str) -> None:
    """Importing a CLI assembly module must not pull in any heavy command dependency."""
    # Run in a fresh interpreter so the test suite's own imports don't pollute sys.modules.
    snippet = (
        "import sys\n"
        f"import {assembly_module}\n"
        f"forbidden = set({FORBIDDEN_AT_IMPORT!r})\n"
        "tops = {name.split('.')[0] for name in sys.modules}\n"
        "print(' '.join(sorted(forbidden & tops)))\n"
    )
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", snippet], capture_output=True, text=True, check=True
    )

    leaked = result.stdout.split()
    assert not leaked, (
        f"Importing {assembly_module} pulled in heavy modules at import time: {leaked}. "
        "Move those imports inside the command function body so `gptnt --help` stays fast."
    )
