"""Validate a model config — used by the `validate` and `doctor` CLI commands.

- :func:`validate_model_config` (static): compose `player.yaml` + `player=<name>`
  (+ `player/provider=<provider>`) and instantiate it — i.e. prove the YAML is correct.
  Credential-tolerant: an unset provider key is reported as `missing_credential` (with
  pydantic-ai's own "set the X environment variable" message retained in `error`), not a
  failure. Instantiation *is* the credential check — there is no separate hardcoded
  provider→env-var map to maintain; pydantic-ai owns which key each provider needs.
- :func:`live_check_model_config` (live, SPENDS MONEY): send one plain-text request and
  report whether the endpoint answers. That is all — we check that it *connects*, not
  what it can do. If a model can't do what its config claims, that is the user's problem
  and surfaces at run time, not here.

Secret safety: an error message may name an env var, but no env var VALUE is ever read,
logged, or returned by this module.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from hydra.errors import HydraException, InstantiationException
from hydra.utils import instantiate
from omegaconf import DictConfig, OmegaConf
from omegaconf.errors import OmegaConfBaseException
from pydantic_ai.exceptions import AgentRunError, UserError

from gptnt.common.hydra import compose_player_config

if TYPE_CHECKING:
    from gptnt.specification import PlayerCapabilities

_ErrorStage = Literal["compose", "capabilities", "agent"]


@dataclass(frozen=True)
class ModelValidationResult:
    """Outcome of a static model-config validation.

    `ok` stays `True` when the only problem is an unset provider key (`missing_credential`).
    """

    model_name: str
    provider: str | None
    ok: bool
    capabilities: PlayerCapabilities | None = None
    resolved_model_name: str | None = None
    missing_credential: bool = False
    error_stage: _ErrorStage | None = None
    error: str | None = None


@dataclass(frozen=True)
class LiveCheckResult:
    """Outcome of a single plain-text request: did the endpoint answer?"""

    ok: bool
    latency_seconds: float | None = None
    response_text: str | None = None
    error: str | None = None


# TODO: We ripped out the @provider stuff so this shouldnt be saying this stuff anymore. I think
#       its still needed though.
def _provider_pairing_error(cfg: DictConfig, model_name: str, provider: str | None) -> str | None:
    """Flag the tier-1-string-model + `@provider` mismatch before it fails cryptically.

    A provider merges under `...agent.model`. A tier-2 explicit model keeps its `_target_`; a
    tier-1 *string* model is replaced by a bare `{provider: ...}` dict (its class lost), which then
    fails deep inside Agent construction.
    """
    if provider is None:
        return None
    model_node = OmegaConf.select(cfg, "player.action_predictor.agent.model")
    if isinstance(model_node, DictConfig) and "_target_" not in model_node:
        return (
            f"Model '{model_name}' uses the tier-1 string form (`model: <provider>:<name>`), which "
            f"cannot take a '@{provider}' provider override. Switch to the explicit `_target_` model "
            "form (tier-2 in the `gptnt new player` scaffold) to attach a custom endpoint."
        )
    return None


def _validate_agent(
    cfg: DictConfig, model_name: str, provider: str | None, capabilities: PlayerCapabilities
) -> ModelValidationResult:
    """Instantiate the agent and classify the outcome (ok / missing-credential / agent error).

    An unset provider key isn't a malformed config — instantiation IS the credential check.
    pydantic-ai's message names the missing env var, and hydra keeps it in the wrapped message, so
    we retain it (in `error`) for the caller to surface. We never read the value itself — only
    pydantic-ai's own "set the X environment variable" text.
    """
    try:
        agent = instantiate(cfg.player.action_predictor.agent)
    except InstantiationException as exc:
        detail = str(exc)
        if "environment variable" in detail:
            return ModelValidationResult(
                model_name,
                provider,
                ok=True,
                capabilities=capabilities,
                missing_credential=True,
                error=detail,
            )
        return ModelValidationResult(
            model_name,
            provider,
            ok=False,
            capabilities=capabilities,
            error_stage="agent",
            error=detail,
        )

    model = agent.model
    resolved = model if isinstance(model, str) else getattr(model, "model_name", None)
    return ModelValidationResult(
        model_name, provider, ok=True, capabilities=capabilities, resolved_model_name=resolved
    )


def validate_model_config(model_name: str, provider: str | None = None) -> ModelValidationResult:
    """Statically validate a model config: compose + instantiate it, then discard.

    Credential-tolerant — an unset provider key reports `ok=True, missing_credential=True`.
    """
    try:
        cfg = compose_player_config(model_name, provider)
    except (HydraException, OmegaConfBaseException) as exc:
        return ModelValidationResult(
            model_name, provider, ok=False, error_stage="compose", error=str(exc)
        )

    try:
        capabilities = instantiate(cfg.player.capabilities)
    except InstantiationException as exc:
        return ModelValidationResult(
            model_name, provider, ok=False, error_stage="capabilities", error=str(exc)
        )

    pairing_error = _provider_pairing_error(cfg, model_name, provider)
    if pairing_error is not None:
        return ModelValidationResult(
            model_name,
            provider,
            ok=False,
            capabilities=capabilities,
            error_stage="agent",
            error=pairing_error,
        )

    return _validate_agent(cfg, model_name, provider, capabilities)


async def live_check_model_config(model_name: str, provider: str | None = None) -> LiveCheckResult:
    """Send ONE plain-text request to prove the endpoint connects.

    SPENDS MONEY.
    """
    try:
        agent = instantiate(
            compose_player_config(model_name, provider).player.action_predictor.agent
        )
    except (HydraException, OmegaConfBaseException) as exc:
        return LiveCheckResult(ok=False, error=str(exc))

    start = time.perf_counter()
    try:
        response = await agent.run("Reply with the single word: READY.")
    except (AgentRunError, UserError) as exc:
        return LiveCheckResult(ok=False, error=str(exc))
    return LiveCheckResult(
        ok=True,
        latency_seconds=time.perf_counter() - start,
        response_text=str(response.output)[:200],
    )
