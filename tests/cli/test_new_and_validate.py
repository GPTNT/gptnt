"""Tests for the `gptnt new` scaffolding and the doctor model-validation rendering.

Pure-function coverage (templates, name validation) plus an integration test of the scaffold ->
validate loop against the real configs dir (with guaranteed cleanup): `gptnt new player <name>`
then `gptnt doctor` (which folds in the old standalone `validate`).
"""

from __future__ import annotations

import io

import pytest
import yaml
from rich.console import Console

from gptnt.cli.__main__ import build_app
from gptnt.cli.doctor import checks, render
from gptnt.cli.doctor.validation import validate_model_config
from gptnt.cli.player.new import _validate_name
from gptnt.cli.player.templates import PLAYER_TEMPLATE, PROVIDER_TEMPLATE
from gptnt.common.paths import Paths

from tests._cli_runner import invoke_cli

_SCAFFOLD_NAME = "_pytest_scaffold_model"


@pytest.mark.parametrize("template", [PLAYER_TEMPLATE, PROVIDER_TEMPLATE])
def test_templates_render_without_placeholder_and_parse(template: str) -> None:
    rendered = template.replace("<NAME>", "peekaboo")
    assert "<NAME>" not in rendered
    # The `${oc.env:...}` lines live inside comments, so plain YAML parsing must succeed.
    assert yaml.safe_load(rendered) is not None


@pytest.mark.parametrize("bad_name", ["", "with space", "a/b", "..", "dot.name"])
def test_validate_name_rejects_unsafe_names(bad_name: str) -> None:
    with pytest.raises(ValueError, match="invalid name"):
        _validate_name(str, bad_name)


@pytest.mark.parametrize("good_name", ["peekaboo", "vllm_box1", "my-model"])
def test_validate_name_accepts_safe_names(good_name: str) -> None:
    assert (
        _validate_name(str, good_name) is None
    )  # the cyclopts validator returns None on success


def test_new_model_success_through_cli() -> None:
    """`gptnt new player <name>` writes the config and points at `gptnt doctor`."""
    target = Paths().configs / "player" / f"{_SCAFFOLD_NAME}.yaml"
    try:  # noqa: WPS501
        result = invoke_cli(build_app(), ["new", "player", _SCAFFOLD_NAME])
        assert result.exit_code == 0, result.output
        assert target.exists()
        assert "Created config" in result.output
        assert "gptnt doctor" in result.output
    finally:
        target.unlink(missing_ok=True)


def test_new_provider_success_through_cli() -> None:
    """`gptnt new provider <name>` writes the provider config under `player/provider/`."""
    target = Paths().configs / "player" / "provider" / f"{_SCAFFOLD_NAME}.yaml"
    try:  # noqa: WPS501
        result = invoke_cli(build_app(), ["new", "provider", _SCAFFOLD_NAME])
        assert result.exit_code == 0, result.output
        assert target.exists()
        assert "Created config" in result.output
    finally:
        target.unlink(missing_ok=True)


def test_scaffold_then_validate_loop() -> None:
    """`new player <name>` produces a config that statically validates (the happy path)."""
    target = Paths().configs / "player" / f"{_SCAFFOLD_NAME}.yaml"
    try:  # noqa: WPS501
        result = invoke_cli(build_app(), ["new", "player", _SCAFFOLD_NAME])
        assert result.exit_code == 0, result.output
        assert target.exists()

        outcome = validate_model_config(_SCAFFOLD_NAME)
        assert outcome.ok
        assert outcome.capabilities is not None
        assert outcome.capabilities.player_name == _SCAFFOLD_NAME
    finally:
        target.unlink(missing_ok=True)


def test_new_model_refuses_overwrite_through_cli() -> None:
    """A second scaffold of the same name fails (raises) instead of overwriting."""
    target = Paths().configs / "player" / f"{_SCAFFOLD_NAME}.yaml"
    try:  # noqa: WPS501
        assert invoke_cli(build_app(), ["new", "player", _SCAFFOLD_NAME]).exit_code == 0
        # The "already exists" guard raises a real exception that propagates (no exit machinery).
        with pytest.raises(FileExistsError, match="already exists"):
            _ = invoke_cli(build_app(), ["new", "player", _SCAFFOLD_NAME])
    finally:
        target.unlink(missing_ok=True)


@pytest.mark.parametrize("evil_name", ["../evil", "a/b", "..", "with space"])
def test_new_model_rejects_traversal_through_cli(evil_name: str) -> None:
    """The `_validate_name` callback fires on the CLI parse path and rejects unsafe names.

    This is the latent hole: a direct `new_player("../evil")` call skips the callback entirely, so
    only the `CliRunner` path actually exercises the guard.
    """
    target = Paths().configs / "player" / f"{evil_name}.yaml"
    result = invoke_cli(build_app(), ["new", "player", evil_name])
    assert result.exit_code != 0
    assert not target.exists()  # nothing was written outside the configs dir


@pytest.mark.anyio
async def test_doctor_model_detailed_view_for_a_real_config() -> None:
    """`doctor` renders a credential-free config (test_random) as a passing detail row."""
    matrix = await checks.check_models([("test_random", None)], live=False)
    detail = matrix.details[0]
    assert detail.static.ok
    assert detail.report.exists == "pass"
    assert detail.report.instantiates == "pass"
    # The renderer prints every resolved field (player name from the SAME validation).
    out = io.StringIO()
    render.render_models(Console(file=out, width=160), matrix.details)
    rendered = out.getvalue()
    assert "test_random" in rendered
    assert "Player" in rendered  # the resolved-field columns are present
