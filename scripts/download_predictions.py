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


def extract_example_data(child: WeaveObject) -> dict[str, Any]:
    """Extract example input data from a child call."""
    row = {}

    if not hasattr(child, "inputs"):
        return row
    if not child.inputs:
        return row
    if not isinstance(child.inputs, dict):
        return row
    if "example" not in child.inputs:
        return row

    example = child.inputs["example"]
    if isinstance(example, dict):
        row.update(flatten_dict(example, "example."))
    else:
        row["example"] = str(example)

    return row


def extract_output_data(child: WeaveObject) -> dict[str, Any]:
    """Extract prediction output data from a child call."""
    row = {}

    if not hasattr(child, "output"):
        return row
    if not child.output:
        return row
    if not isinstance(child.output, dict):
        return row

    output = child.output

    if "output" in output:
        output_val = output["output"]
        if isinstance(output_val, dict):
            row.update(flatten_dict(output_val, "prediction."))
        else:
            row["prediction"] = str(output_val)

    if "scores" in output:
        scores = output["scores"]
        if isinstance(scores, dict):
            row.update(flatten_dict(scores, "score."))

    if "model_latency" in output:
        latency = output["model_latency"]
        if isinstance(latency, dict):
            row.update(flatten_dict(latency, "latency."))
        else:
            row["latency"] = latency

    return row


def process_child_call(child: WeaveObject, i: int, log: Any) -> dict[str, Any] | None:
    """Process a single child call and extract prediction data."""
    try:
        row = {"prediction_call_id": child.id}
        row.update(extract_example_data(child))
        row.update(extract_output_data(child))
    except (AttributeError, KeyError, TypeError) as e:
        log.warning("failed_to_process_child", child_index=i, error=str(e))
        return None

    return row


def get_evaluation_predictions(client: Any, eval_call: WeaveObject) -> list[dict[str, Any]]:
    """Fetch all prediction rows from an evaluation call."""
    predictions = []
    log = logger.bind(eval_call_id=eval_call.id)

    try:
        log.info("fetching_child_calls")
        children = list(client.get_calls(filter=CallsFilter(parent_ids=[eval_call.id])))
        log.info("child_calls_fetched", count=len(children))

        for i, child in enumerate(children):
            row = process_child_call(child, i, log)
            if row:
                predictions.append(row)

        log.info("predictions_extracted", count=len(predictions))

    except Exception as e:
        log.exception("failed_to_fetch_predictions", error=str(e))

    return predictions


def add_model_metadata(
    predictions: list[dict[str, Any]], match: str, name: str, call_id: str
) -> None:
    """Add model metadata to each prediction row."""
    for pred in predictions:
        pred["model_group"] = match
        pred["model_full_name"] = name
        pred["eval_call_id"] = call_id


def save_individual_predictions(
    output_dir: Path, predictions_by_model: dict[str, list[dict[str, Any]]]
) -> None:
    """Save individual prediction files for each model."""
    for model_group, predictions in predictions_by_model.items():
        if not predictions:
            continue

        pred_df = pd.DataFrame(predictions)
        pred_path = output_dir / f"{model_group}_predictions.csv"
        pred_df.to_csv(pred_path, index=False)
        logger.info(
            "saved_predictions", file=str(pred_path), model=model_group, rows=len(predictions)
        )


def save_combined_predictions(
    output_dir: Path, predictions_by_model: dict[str, list[dict[str, Any]]]
) -> None:
    """Save combined predictions file with all models."""
    all_predictions = []
    for predictions in predictions_by_model.values():
        all_predictions.extend(predictions)

    if not all_predictions:
        return

    combined_df = pd.DataFrame(all_predictions)
    combined_path = output_dir / "all_models_predictions.csv"
    combined_df.to_csv(combined_path, index=False)
    logger.info(
        "saved_combined_predictions", file=str(combined_path), total_rows=len(all_predictions)
    )


def find_matching_model(name: str | None) -> str | None:
    """Find a target model that matches the given name."""
    if not name:
        return None
    return next((t for t in TARGET_MODELS if t in name), None)


def process_command(cmd: str) -> None:
    """Fetch evaluation predictions for a single command and save to CSV."""
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

    predictions_by_model: dict[str, list[dict[str, Any]]] = {}

    for call in evals:
        if len(predictions_by_model) >= len(TARGET_MODELS):
            break

        name = extract_model_name(call)
        match = find_matching_model(name)

        if not match or not name:
            continue
        if match in predictions_by_model:
            continue

        log.info("found", target=match, model=name)
        log.info("fetching_predictions", target=match, model=name)

        predictions = get_evaluation_predictions(client, call)

        if not predictions:
            log.warning("no_predictions_found", target=match)
            continue

        add_model_metadata(predictions, match, name, call.id)
        predictions_by_model[match] = predictions
        log.info("fetched_predictions", target=match, count=len(predictions))

    missing = set(TARGET_MODELS) - set(predictions_by_model.keys())
    if missing:
        log.warning("missing", models=missing)

    if not predictions_by_model:
        log.warning("no_predictions_data")
        return

    output_dir = OUTPUT_BASE_DIR / f"{cmd}_results" / "predictions"
    output_dir.mkdir(parents=True, exist_ok=True)

    save_individual_predictions(output_dir, predictions_by_model)
    save_combined_predictions(output_dir, predictions_by_model)


def main() -> None:
    """Entry point: process all commands and save CSVs."""
    for cmd in PROJECT_MAP:
        process_command(cmd)


if __name__ == "__main__":
    main()
