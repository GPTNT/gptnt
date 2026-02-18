from pathlib import Path
from typing import Any

import pandas as pd
import structlog
import weave
from weave.trace.vals import WeaveObject
from weave.trace.weave_client import CallsFilter
from weave.trace_server.trace_server_interface import SortBy

structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ]
)
logger = structlog.get_logger()

PROJECT_MAP: dict[str, str] = {
    "defuser-grounding-coordinates": "gptnt/defuser-grounding-coordinates",
    "defuser-grounding-som": "gptnt/defuser-grounding-som",
    "defuser-vqa-oe": "gptnt/defuser-vqa-open_ended",
    "defuser-vqa-mcq": "gptnt/defuser-vqa-mcq",
    "expert-vqa": "gptnt/expert-vqa",
    "expert-ocr": "gptnt/expert-ocr",
    "expert-element-grounding": "gptnt/expert-element-grounding",
}

TARGET_MODELS: list[str] = [
    "gemini-3-flash-preview",
    "claude-sonnet-4-5",
    "gpt-5.2",
    "internvl35",
    "qwen3vl",
]

OUTPUT_BASE_DIR: Path = Path("storage/outputs")


def extract_model_name(call: WeaveObject) -> str | None:
    """Extract the model name from an evaluation call's inputs."""
    try:
        v = call.inputs.get("model")
    except (AttributeError, KeyError, TypeError):
        return None

    if v is None:
        return None
    if hasattr(v, "name"):
        return v.name
    if isinstance(v, dict) and "name" in v:
        return v["name"]
    return str(v)


def flatten_dict(d: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    """Recursively flatten a nested dictionary into dot-separated keys."""
    out: dict[str, Any] = {}
    for k, v in d.items():
        key = f"{prefix}{k}" if prefix else k
        if isinstance(v, dict):
            out.update(flatten_dict(v, f"{key}."))
        else:
            out[key] = v
    return out


def create_summary_row(call: WeaveObject, match: str, name: str) -> dict[str, Any]:
    """Create a summary row from an evaluation call."""
    row: dict[str, Any] = {
        "model_group": match,
        "model_full_name": name,
        "call_id": call.id,
        "started_at": str(call.started_at) if call.started_at else None,
    }

    has_output = call.output and isinstance(call.output, dict)
    has_summary = call.summary and isinstance(call.summary, dict)

    if has_output:
        row.update(flatten_dict(call.output))
    elif has_summary:
        row.update(flatten_dict(call.summary))

    return row


def find_matching_model(name: str | None) -> str | None:
    """Find a target model that matches the given name."""
    if not name:
        return None
    return next((t for t in TARGET_MODELS if t in name), None)


def process_command(cmd: str) -> None:
    """Fetch evaluation summaries for a single command and save to CSV."""
    slug = PROJECT_MAP[cmd]
    log = logger.bind(command=cmd, project=slug)
    log.info("processing")

    client = weave.init(slug)

    op_pattern = f"weave:///{slug}/op/Evaluation.evaluate:*"
    log.info("fetching", pattern=op_pattern)

    evals = list(
        client.get_calls(
            filter=CallsFilter(op_names=[op_pattern]),
            sort_by=[SortBy(field="started_at", direction="desc")],
        )
    )
    log.info("fetched", count=len(evals))

    found: dict[str, dict[str, Any]] = {}

    for call in evals:
        if len(found) >= len(TARGET_MODELS):
            break

        name = extract_model_name(call)
        match = find_matching_model(name)

        if not match or not name:
            continue
        if match in found:
            continue

        log.info("found", target=match, model=name)
        found[match] = create_summary_row(call, match, name)

    missing = set(TARGET_MODELS) - set(found)
    if missing:
        log.warning("missing", models=missing)

    if not found:
        log.warning("no_data")
        return

    df = pd.DataFrame(list(found.values()))
    output_dir = OUTPUT_BASE_DIR / f"{cmd}_results"
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "results_summary.csv"
    df.to_csv(path, index=False)
    log.info("saved", file=str(path), models=list(found.keys()))


def main() -> None:
    """Entry point: process all commands and save CSVs."""
    for cmd in PROJECT_MAP:
        process_command(cmd)


if __name__ == "__main__":
    main()
