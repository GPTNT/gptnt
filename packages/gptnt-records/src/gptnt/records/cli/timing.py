"""Summarise LLM inference time vs framework overhead for an experiment run.

Reads the per-process span-timing JSONL written when
`OBSERVABILITY_CAPTURE_SPAN_TIMINGS=1` is set (see `gptnt.core.common.span_timing`) and,
per player, splits each forward pass into:

    inference   = sum(duration of pydantic-ai "chat *" spans)  ← actual model inference
    framework   = duration("player forward pass") - inference   ← harness overhead
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

import structlog
import typer
from rich.console import Console
from rich.table import Table

if TYPE_CHECKING:
    import polars as pl

console = Console()
logger = structlog.get_logger()


# ── data transforms ──────────────────────────────────────────────────────────


def _per_step_df(df: pl.DataFrame) -> pl.DataFrame:
    """One row per forward pass with inference and framework times split out.

    Joins on parent_span_id chain rather than trace_id to avoid the case where
    multiple forward passes share a trace (e.g. both players in one session), which
    would cause the whole-session inference total to be attributed to every step.

    Chain: "player forward pass" → "Send request to agent" → pydantic-ai "chat *"
    """
    import polars as pl

    forward_passes = df.filter(pl.col("name") == "player forward pass").select(
        ["session_id", "player_role", "model_name", "span_id", pl.col("duration_s").alias("total")]
    )

    # "Send request to agent" spans are direct children of "player forward pass".
    agent_spans = df.filter(pl.col("name") == "Send request to agent").select(
        ["span_id", "parent_span_id"]
    )

    # pydantic-ai "chat *" spans are children of "Send request to agent".
    # Group by their parent so each agent_span gets its own inference total —
    # handles tool-use loops where one forward pass triggers multiple model calls.
    inference_per_agent_span = (
        df.filter(
            (pl.col("otel_scope_name") == "pydantic-ai") & pl.col("name").str.starts_with("chat ")
        )
        .group_by("parent_span_id")
        .agg(pl.sum("duration_s").alias("inference"))
    )

    # agent_span.span_id → inference, then forward_pass.span_id → agent_span.parent_span_id
    agent_with_inference = agent_spans.join(
        inference_per_agent_span, left_on="span_id", right_on="parent_span_id", how="left"
    ).select(pl.col("parent_span_id").alias("span_id"), pl.col("inference").fill_null(0))

    return forward_passes.join(agent_with_inference, on="span_id", how="left").select(
        [
            "session_id",
            "player_role",
            "model_name",
            "total",
            pl.col("inference").fill_null(0),
            (pl.col("total") - pl.col("inference").fill_null(0)).alias("framework"),
        ]
    )


def _per_player_df(steps: pl.DataFrame) -> pl.DataFrame:
    import polars as pl

    return (
        steps.group_by(["session_id", "player_role"])
        .agg(
            [
                pl.first("model_name"),
                pl.len().alias("steps"),
                pl.sum("inference"),
                pl.sum("framework"),
                pl.sum("total"),
            ]
        )
        .sort(["model_name", "session_id", "player_role"])
    )


def _phase_df(df: pl.DataFrame) -> pl.DataFrame:
    import polars as pl

    # Normalise pydantic-ai "chat <model>" span names so they aggregate cleanly.
    not_game = pl.col("player_role").is_null() | (pl.col("player_role") != "game")
    is_chat_span = (pl.col("otel_scope_name") == "pydantic-ai") & pl.col("name").str.starts_with(
        "chat "
    )
    return (
        df.filter(not_game)
        .with_columns(
            pl.when(is_chat_span)
            .then(pl.lit("pydantic-ai (chat)"))
            .otherwise(pl.col("name"))
            .alias("name")
        )
        .group_by("name")
        .agg(
            [
                pl.len().alias("count"),
                pl.sum("duration_s").alias("total"),
                pl.mean("duration_s").alias("avg"),
                pl.quantile("duration_s", 0.95).alias("p95"),
                pl.quantile("duration_s", 0.99).alias("p99"),
            ]
        )
        .sort("total", descending=True)
    )


# ── table builders ────────────────────────────────────────────────────────────


def _format_darwin_gpu(gpu: dict[str, Any]) -> str:
    """Render one `system_profiler` GPU entry as ``name (N cores), VRAM``."""
    name = gpu.get("sppci_model") or gpu.get("_name", "unknown")
    cores = gpu.get("sppci_cores")
    vram = gpu.get("spdisplays_vram") or gpu.get("sppci_vram")
    return "".join((name, f" ({cores} cores)" if cores else "", f", {vram} VRAM" if vram else ""))


def _query_darwin_gpu() -> str:
    raw = subprocess.check_output(
        ["/usr/sbin/system_profiler", "SPDisplaysDataType", "-json"],
        stderr=subprocess.DEVNULL,
        timeout=5,
    )
    gpus = json.loads(raw).get("SPDisplaysDataType", [])
    parts = [_format_darwin_gpu(gpu) for gpu in gpus]
    return " | ".join(parts) if parts else "unknown"


def _query_linux_gpu() -> str:
    raw = subprocess.check_output(
        ["/usr/bin/lspci"], stderr=subprocess.DEVNULL, timeout=5
    ).decode()
    tags = ("VGA", "3D controller", "Display controller")
    gpus = [
        line.split(": ", 1)[1].strip()
        for line in raw.splitlines()
        if any(tag in line for tag in tags)
    ]
    return " | ".join(gpus) if gpus else "unknown"


def _query_gpu() -> str:
    """Return a human-readable GPU string using only OS-level tools (no drivers required)."""
    queriers = {"Darwin": _query_darwin_gpu, "Linux": _query_linux_gpu}
    querier = queriers.get(platform.system())
    if querier is None:
        return "unknown"
    try:
        return querier()
    except Exception:  # noqa: BLE001
        logger.debug("GPU query failed", exc_info=True)
        return "unknown"


def _build_machine_table() -> Table:
    import psutil

    table = Table(title="Machine")
    table.add_column("property", justify="left")
    table.add_column("value", justify="left")

    mem = psutil.virtual_memory()
    mem_gb = mem.total / (1024**3)

    cpu_freq = psutil.cpu_freq()
    freq_str = f" @ {cpu_freq.max / 1000:.2f} GHz" if cpu_freq else ""
    cpu_str = (
        f"{platform.processor() or platform.machine()}{freq_str} ({os.cpu_count()} logical cores)"
    )

    rows = [
        ("hostname", platform.node()),
        ("os", f"{platform.system()} {platform.release()} ({platform.machine()})"),
        ("cpu", cpu_str),
        ("ram", f"{mem_gb:.1f} GB total"),
        ("gpu", _query_gpu()),
        ("python", platform.python_version()),
    ]
    for prop, prop_value in rows:
        table.add_row(prop, prop_value)
    return table


def _build_player_table(df: pl.DataFrame) -> Table:
    table = Table(title="Average time per forward pass — per player")
    for col in ("model", "session", "role"):
        table.add_column(col, justify="left")
    for col in ("steps", "avg inference (s)", "avg framework (s)", "avg total (s)"):
        table.add_column(col, justify="right")
    for row in df.iter_rows(named=True):
        steps = row["steps"]
        table.add_row(
            str(row["model_name"] or "?"),
            str(row["session_id"])[:8],
            str(row["player_role"]),
            str(steps),
            f"{row['inference'] / steps:.2f}",
            f"{row['framework'] / steps:.2f}",
            f"{row['total'] / steps:.2f}",
        )
    return table


def _build_phase_table(df: pl.DataFrame) -> Table:
    table = Table(title="Span breakdown — avg / p95 / p99 across run")
    table.add_column("span", justify="left")
    for col in ("count", "avg (s)", "p95 (s)", "p99 (s)", "total (s)"):
        table.add_column(col, justify="right")
    for row in df.iter_rows(named=True):
        table.add_row(
            str(row["name"]),
            str(row["count"]),
            f"{row['avg']:.3f}",
            f"{row['p95']:.3f}",
            f"{row['p99']:.3f}",
            f"{row['total']:.1f}",
        )
    return table


def _scalar_or_zero(df: pl.DataFrame, expr: pl.Expr) -> float:
    """Evaluate a one-cell aggregate, treating an empty/null result as zero."""
    return df.select(expr).item() or 0


def _add_benchmark_row(table: Table, df: pl.DataFrame, label: str) -> None:
    """Append one role's avg framework/inference/total step times to `table`."""
    import polars as pl

    avg_fw = _scalar_or_zero(df, pl.col("framework").cast(pl.Float64).mean())
    std_fw = _scalar_or_zero(df, pl.col("framework").cast(pl.Float64).std())
    avg_inf = _scalar_or_zero(df, pl.col("inference").cast(pl.Float64).mean())
    table.add_row(
        label,
        str(len(df)),
        f"{avg_fw:.3f}",
        f"{std_fw:.3f}",
        f"{avg_inf:.3f}",
        f"{avg_fw + avg_inf:.3f}",
    )


def _build_benchmark_table(step_df: pl.DataFrame) -> Table:
    import polars as pl

    table = Table(title="Benchmark summary — avg per step by role")
    table.add_column("role", justify="left")
    for col in ("steps", "avg framework (s)", "± stddev", "avg inference (s)", "avg total (s)"):
        table.add_column(col, justify="right")

    roles = step_df["player_role"].drop_nulls().unique().sort().to_list()
    for role in roles:
        _add_benchmark_row(table, step_df.filter(pl.col("player_role") == role), role)
    if len(roles) > 1:
        table.add_section()
        _add_benchmark_row(table, step_df, "all")

    return table


# ── entry point ───────────────────────────────────────────────────────────────


def query_span_timings(
    *,
    run_dir: Annotated[
        Path,
        typer.Argument(
            help="Run output directory containing span_timings/*.jsonl.",
            exists=True,
            file_okay=False,
        ),
    ],
) -> None:
    """Summarise LLM inference time vs framework overhead for an experiment run."""
    import polars as pl

    timing_files = sorted(run_dir.rglob("span_timings/*.jsonl"))
    if not timing_files:
        console.print(
            f"[yellow]No span_timings/*.jsonl found under {run_dir}.[/yellow] "
            "Re-run with [bold]OBSERVABILITY_CAPTURE_SPAN_TIMINGS=1[/bold] to capture timings."
        )
        raise typer.Exit(code=1)

    df = pl.concat(
        [pl.read_ndjson(timing_file) for timing_file in timing_files], how="diagonal_relaxed"
    )
    if "otel_scope_name" not in df.columns:
        df = df.with_columns(pl.lit(None, dtype=pl.String).alias("otel_scope_name"))

    step_df = _per_step_df(df)
    player_df = _per_player_df(step_df)

    console.print(_build_machine_table())
    console.print(_build_player_table(player_df))
    console.print(_build_phase_table(_phase_df(df)))

    console.print(_build_benchmark_table(step_df))
