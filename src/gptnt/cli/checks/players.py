"""`gptnt doctor` player-model checks: does each config compose, instantiate, and answer?"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from gptnt.cli.checks.result import CheckResult, CheckStatus
from gptnt.cli.checks.validation import (
    ModelValidationResult,
    live_check_model_config,
    validate_model_config,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from gptnt.cli.checks.validation import LiveCheckResult


@dataclass(frozen=True)
class PlayerReport:
    """One model across three independent boxes: exists → instantiates → live.

    The boxes are hierarchical (a box can't pass if its predecessor failed), so a failed box leaves
    the downstream ones as `skip`.
    """

    label: str

    exists: CheckStatus
    """The config is found and the YAML composes."""

    instantiates: CheckStatus
    """It builds into a working `pydantic_ai.Agent`.

    ✗ when the build fails, which includes an unset provider credential: the config composes but
    cannot run, so the doctor fails it rather than warning.
    """

    live: CheckStatus
    """A real request answered (only run under `--live`; `skip` otherwise)."""

    note: str = ""

    @property
    def failed(self) -> bool:
        """True if any box that actually ran failed (`warn`/`skip` never fail the run)."""
        return "fail" in {self.exists, self.instantiates, self.live}


@dataclass(frozen=True)
class PlayerDetail:
    """One model's full validation result: the ✓/✗ boxes plus the underlying data."""

    report: PlayerReport
    """The matrix-compatible boxes that drive the failed/exit decision."""

    static: ModelValidationResult
    """Every resolved field, so the detailed rows can be rendered."""

    live: LiveCheckResult | None = None
    """The real-request result when `--live` ran, else `None`."""


@dataclass(frozen=True)
class PlayerMatrix:
    """Every model's detail plus the config-name → player_name mapping."""

    details: list[PlayerDetail]

    config_to_player: dict[str, str | None]
    """Each config name mapped to its resolved `player_name`, from the same `validate_model_config`
    pass that builds `details`, so the report and the run-plan roster resolution cannot disagree.

    `None` when the config did not instantiate far enough to yield a `capabilities.player_name`.
    """

    @property
    def reports(self) -> list[PlayerReport]:
        """The matrix-compatible ✓/✗ boxes, one per model."""
        return [detail.report for detail in self.details]


async def check_players(targets: Sequence[tuple[str, str | None]], *, live: bool) -> PlayerMatrix:
    """Validate each model into its full detail (boxes + every resolved field + optional live).

    Also returns a `config name → player_name` mapping derived from the same validation, so the
    run-plan cross-check can resolve roster configs without composing twice. Empty `targets` yields
    empty `details` (the caller renders the "no configs" message and fails).

    Runs sequentially on purpose: `validate_model_config` clears the global Hydra singleton on
    every call, so concurrent composition would race.
    """
    details: list[PlayerDetail] = []
    config_to_player: dict[str, str | None] = {}
    for model_name, provider in targets:
        label = model_name if provider is None else f"{model_name}@{provider}"
        try:
            # Sequential await is required: validate_model_config clears the global Hydra
            # singleton on each call, so models cannot be composed concurrently.
            detail = await _player_detail(label, model_name, provider, live=live)  # noqa: WPS476
        except Exception as exc:  # noqa: BLE001 — isolate one bad config from the rest of the run
            crashed = ModelValidationResult(model_name, provider, ok=False, error=str(exc))
            detail = PlayerDetail(
                PlayerReport(label, "fail", "skip", "skip", f"check crashed: {exc}"), crashed
            )
        details.append(detail)
        capabilities = detail.static.capabilities
        config_to_player[model_name] = capabilities.player_name if capabilities else None
    return PlayerMatrix(details, config_to_player)


async def _player_detail(
    label: str, model_name: str, provider: str | None, *, live: bool
) -> PlayerDetail:
    """Validate one model into its full detail (boxes + resolved fields + optional live result)."""
    static = validate_model_config(model_name, provider)
    exists, instantiates, note = _static_boxes(static)
    # Live only runs when requested AND the model instantiated (a ✗ instantiate — a build error or
    # an unset credential — leaves nothing to call).
    if not (live and exists == "pass" and instantiates == "pass"):
        return PlayerDetail(PlayerReport(label, exists, instantiates, "skip", note), static)

    outcome = await live_check_model_config(model_name, provider)
    if outcome.ok:
        report = PlayerReport(
            label, exists, instantiates, "pass", f"answered in {outcome.latency_seconds:.2f}s"
        )
    else:
        report = PlayerReport(label, exists, instantiates, "fail", outcome.error or "")
    return PlayerDetail(report, static, outcome)


def check_tokens_per_image(details: Sequence[PlayerDetail]) -> list[CheckResult]:
    """One row per player: is its per-image token cost calibrated (non-zero)?

    `capabilities.tokens_per_image` stays `0` until `gptnt measure-tokens-per-image` measures it
    against the live model. A `0` makes the token accountant undercount image tokens, so it fails
    here with the exact fix. Players whose config did not instantiate are skipped — the model
    matrix already fails them.
    """
    rows: list[CheckResult] = []
    for detail in details:
        if detail.report.instantiates != "pass":
            continue
        capabilities = detail.static.capabilities
        if capabilities is None:
            continue
        config_name = detail.static.model_name
        if capabilities.tokens_per_image > 0:
            rows.append(
                CheckResult(config_name, "pass", f"{capabilities.tokens_per_image} tokens/image")
            )
        else:
            rows.append(
                CheckResult(
                    config_name,
                    "fail",
                    "uncalibrated (0 tokens/image)",
                    f"Run: gptnt measure-tokens-per-image {config_name}",
                )
            )
    return rows


def _static_boxes(outcome: ModelValidationResult) -> tuple[CheckStatus, CheckStatus, str]:
    """Map a static validation outcome to (exists, instantiates, note).

    Instantiation IS the credential check: an unset provider key is a ✗ carrying pydantic-ai's own
    "set the X environment variable" text — no hardcoded key map to maintain. The doctor fails it
    (a config with no key can't run) even though the raw validator stays credential-tolerant.
    """
    if outcome.error_stage == "compose":  # YAML missing / invalid — nothing to instantiate
        return "fail", "skip", outcome.error or ""
    if not outcome.ok:  # composed, but capabilities/agent failed to build
        return "pass", "fail", outcome.error or ""
    if outcome.missing_credential:
        # Doctor is stricter than validate_model_config here: an unset provider key can't run, so
        # it FAILS the report (the raw validator stays credential-tolerant for other callers).
        return "pass", "fail", outcome.error or ""
    return "pass", "pass", f"resolves to {outcome.resolved_model_name or 'instantiated'}"
