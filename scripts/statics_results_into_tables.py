from pathlib import Path
from typing import cast

import numpy as np
import pandas as pd
import structlog

structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ]
)

logger = structlog.get_logger()

EXCLUDED_MODELS = ["gpt-5.1", "gpt-5.1-chat-latest"]


class DataLoadError(Exception):
    """Raised when data cannot be loaded from CSV files."""


class TableGenerationError(Exception):
    """Raised when table generation fails."""


def normalize_module_name(module_name: str) -> str:
    """Normalize module name to uppercase with no underscores."""
    if not isinstance(module_name, str):
        return str(module_name).upper()

    if "-" in module_name:
        parts = module_name.split("-")
        normalized_parts = [part.replace("_", "").upper() for part in parts]
        normalized = "-".join(normalized_parts)
    else:
        normalized = module_name.replace("_", "").upper()

    if normalized == "VENNWIRES":
        normalized = "VENN"
    if normalized == "MORSE":
        normalized = "MORSECODE"
    if normalized == "BIGBUTTON":
        normalized = "BUTTON"

    if "-" in normalized:
        parts = normalized.split("-")
        parts = ["MORSECODE" if p == "MORSE" else p for p in parts]
        parts = ["BUTTON" if p == "BIGBUTTON" else p for p in parts]
        normalized = "-".join(parts)
    return normalized


def extract_module_columns(
    df: pd.DataFrame, prefix: str = "module."
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Extract module columns, returning mappings for single and multi modules."""
    all_module_names = [
        col.replace(prefix, "").replace(".true_fraction", "")
        for col in df.columns
        if col.startswith(prefix) and ".true_fraction" in col and "total" not in col
    ]

    normalized_map = {name: normalize_module_name(name) for name in all_module_names}
    single_module_mapping: dict[str, list[str]] = {}
    multi_module_mapping: dict[str, list[str]] = {}

    for original, normalized in normalized_map.items():
        if "-" in normalized:
            multi_module_mapping.setdefault(normalized, []).append(original)
            continue
        single_module_mapping.setdefault(normalized, []).append(original)

    return single_module_mapping, multi_module_mapping


def load_task_data(task_name: str, base_path: Path) -> pd.DataFrame:
    """Load data for a specific task from CSV file."""
    file_path = base_path / f"{task_name}_results" / "results_summary.csv"
    if not file_path.exists():
        raise DataLoadError(f"File not found: {file_path}")
    try:
        return cast("pd.DataFrame", pd.read_csv(file_path))
    except pd.errors.EmptyDataError as e:
        raise DataLoadError(f"Empty CSV file: {file_path}") from e
    except OSError as e:
        raise DataLoadError(f"Error loading {file_path}: {e!s}") from e


def load_predictions_data(task_name: str, base_path: Path) -> pd.DataFrame:
    """Load raw predictions data for a specific task."""
    file_path = base_path / f"{task_name}_results" / "predictions" / "all_models_predictions.csv"
    if not file_path.exists():
        logger.warning("predictions_file_not_found", task=task_name)
        return pd.DataFrame()
    try:
        return cast("pd.DataFrame", pd.read_csv(file_path, low_memory=False))
    except (pd.errors.ParserError, pd.errors.EmptyDataError, OSError) as e:
        logger.warning("failed_loading_predictions", task=task_name, error=str(e))
        return pd.DataFrame()


def filter_exclude_models(df: pd.DataFrame, model_col: str = "model_full_name") -> pd.DataFrame:
    """Filter to exclude specific models."""
    if model_col not in df.columns:
        return df
    mask = ~df[model_col].isin(EXCLUDED_MODELS)
    return cast("pd.DataFrame", df[mask].copy())


def get_model_data(df: pd.DataFrame, model: str, model_col: str) -> pd.DataFrame:
    """Get model data from dataframe ensuring it returns a DataFrame."""
    result = df[df[model_col] == model]
    return cast("pd.DataFrame", result)


def calculate_weighted_average_for_module(
    model: str,
    module_variants: list[str],
    dfs: list[pd.DataFrame],
    model_col: str = "model_full_name",
) -> tuple[float, float] | None:
    """Calculate weighted average for a module across multiple dataframes."""
    total_count, total_true = 0.0, 0.0
    for df in dfs:
        model_data = get_model_data(df, model, model_col)
        if model_data.empty:
            continue
        for variant in module_variants:
            c_col, f_col = f"module.{variant}.true_count", f"module.{variant}.true_fraction"
            if c_col not in model_data.columns or f_col not in model_data.columns:
                continue
            c_val = float(model_data[c_col].to_numpy()[0])
            f_val = float(model_data[f_col].to_numpy()[0])
            if pd.isna(c_val) or pd.isna(f_val):
                continue
            if f_val <= 0:
                if c_val == 0:
                    total_count += 1.0
                continue
            total_count += c_val / f_val
            total_true += c_val
            break
    return (total_true / total_count, total_count) if total_count > 0 else None


def calculate_metric_value(
    model_data: pd.DataFrame, metric_prefix_variants: list[str]
) -> tuple[float, float] | None:
    """Calculate metric value from model data."""
    for prefix in metric_prefix_variants:
        c_col, f_col = f"{prefix}.true_count", f"{prefix}.true_fraction"
        if c_col not in model_data.columns or f_col not in model_data.columns:
            continue
        c_val = float(model_data[c_col].to_numpy()[0])
        f_val = float(model_data[f_col].to_numpy()[0])
        if pd.isna(c_val) or pd.isna(f_val):
            continue
        if f_val <= 0:
            return (0.0, 1.0) if c_val == 0 else None
        return (f_val, c_val / f_val)
    return None


def calculate_overall_average(values_with_counts: list[tuple[float, float]]) -> float:
    """Calculate weighted average from list of (value, count) tuples."""
    if not values_with_counts:
        return np.nan
    total_weighted = sum(val * count for val, count in values_with_counts)
    total_count = sum(count for _, count in values_with_counts)
    return total_weighted / total_count if total_count > 0 else np.nan


def collect_all_models(dfs: list[pd.DataFrame], model_col: str) -> list[str]:
    """Collect all unique model names from dataframes."""
    all_models = set()
    for df in dfs:
        if model_col in df.columns:
            all_models.update(df[model_col].unique())
    return sorted([m for m in all_models if m not in EXCLUDED_MODELS])


def generate_manual_vqa_by_module(
    tasks: list[str], base_path: Path, model_col: str = "model_full_name"
) -> pd.DataFrame:
    """Generate Table 1: Manual VQA by Module."""
    dfs = [filter_exclude_models(load_task_data(t, base_path)) for t in tasks]
    all_single_mappings: dict[str, list[str]] = {}
    for df in dfs:
        s_map, _ = extract_module_columns(df)
        for k, v in s_map.items():
            all_single_mappings.setdefault(k, []).extend(v)

    sorted_modules = sorted(all_single_mappings.keys())
    all_models = collect_all_models(dfs, model_col)
    result_data: dict[str, list[float]] = {m: [] for m in [*sorted_modules, "Average"]}

    for name in all_models:
        module_values = []
        for mod in sorted_modules:
            res = calculate_weighted_average_for_module(
                name, list(set(all_single_mappings[mod])), dfs, model_col
            )
            result_data[mod].append(res[0] if res else np.nan)
            if res:
                module_values.append(res)
        result_data["Average"].append(calculate_overall_average(module_values))

    return pd.DataFrame(result_data, index=pd.Index(all_models, name="model"))


def generate_manual_vqa_by_capability(
    base_path: Path, model_col: str = "model_full_name"
) -> pd.DataFrame:
    """Generate Table 2: Manual VQA by Capability."""
    cap_map = {
        "Reading": "expert-ocr",
        "Element Grounding": "expert-element-grounding",
        "Procedural Reasoning": "expert-vqa",
    }
    dfs_map = {c: filter_exclude_models(load_task_data(t, base_path)) for c, t in cap_map.items()}
    all_models = collect_all_models(list(dfs_map.values()), model_col)
    vqa_df = dfs_map["Procedural Reasoning"]

    cols = list(cap_map.keys())
    if "hallucination_type.type_a.total.true_fraction" in vqa_df.columns:
        cols.extend(["Ambiguity", "Hallucination"])
    result_data: dict[str, list[float]] = {c: [] for c in [*cols, "Average"]}

    for name in all_models:
        vals = []
        for cap, df in dfs_map.items():
            res = calculate_metric_value(get_model_data(df, name, model_col), ["module.total"])
            result_data[cap].append(res[0] if res else np.nan)
            if res:
                vals.append(res)

        if "Ambiguity" in result_data:
            res_a = calculate_metric_value(
                get_model_data(vqa_df, name, model_col), ["hallucination_type.type_a.total"]
            )
            res_b = calculate_metric_value(
                get_model_data(vqa_df, name, model_col), ["hallucination_type.type_b.total"]
            )
            result_data["Ambiguity"].append(res_a[0] if res_a else np.nan)
            result_data["Hallucination"].append(res_b[0] if res_b else np.nan)
            if res_a:
                vals.append(res_a)
            if res_b:
                vals.append(res_b)

        result_data["Average"].append(calculate_overall_average(vals))

    return pd.DataFrame(result_data, index=pd.Index(all_models, name="model"))


def generate_simulator_vqa_by_module(
    base_path: Path, model_col: str = "model_full_name"
) -> pd.DataFrame:
    """Generate Table 3: Simulator VQA by Module."""
    df_mcq = filter_exclude_models(load_task_data("defuser-vqa-mcq", base_path))
    df_oe = filter_exclude_models(load_task_data("defuser-vqa-oe", base_path))
    all_models = collect_all_models([df_mcq, df_oe], model_col)
    s_mcq, m_mcq = extract_module_columns(df_mcq)
    s_oe, _ = extract_module_columns(df_oe)

    all_s = {k: list(set(s_mcq.get(k, []) + s_oe.get(k, []))) for k in set(s_mcq) | set(s_oe)}
    sorted_s = sorted(all_s.keys())
    cols = sorted_s + (["Multi-Module Average"] if m_mcq else []) + ["Average"]
    result_data: dict[str, list[float]] = {c: [] for c in cols}

    for name in all_models:
        vals = []
        for mod in sorted_s:
            prefixes = [f"module.{v}" for v in all_s[mod]]
            is_keypad = any("keypad" in v.lower() for v in all_s[mod])
            target_df = df_oe if is_keypad else df_mcq
            res = calculate_metric_value(get_model_data(target_df, name, model_col), prefixes)
            result_data[mod].append(res[0] if res else np.nan)
            if res:
                vals.append(res)
        if m_mcq:
            m_data = get_model_data(df_mcq, name, model_col)
            counts, trues = 0.0, 0.0
            for variants in m_mcq.values():
                res_m = calculate_metric_value(m_data, [f"module.{v}" for v in variants])
                if res_m:
                    trues += res_m[0] * res_m[1]
                    counts += res_m[1]
            avg_m = (trues / counts, counts) if counts > 0 else None
            result_data["Multi-Module Average"].append(avg_m[0] if avg_m else np.nan)
            if avg_m:
                vals.append(avg_m)
        result_data["Average"].append(calculate_overall_average(vals))

    return pd.DataFrame(result_data, index=pd.Index(all_models, name="model"))


def generate_simulator_vqa_by_capability(
    base_path: Path, model_col: str = "model_full_name"
) -> pd.DataFrame:
    """Generate Table 4: Simulator VQA by Capability."""
    df_mcq = filter_exclude_models(load_task_data("defuser-vqa-mcq", base_path))
    df_oe = filter_exclude_models(load_task_data("defuser-vqa-oe", base_path))
    all_models = collect_all_models([df_mcq, df_oe], model_col)

    caps = {
        "Color": ("question_type.color.total", df_mcq),
        "Counting": ("question_type.counting.total", df_mcq),
        "Describing": ("question_type.description.total", df_oe),
        "Indexing": ("question_type.coordinates.total", df_mcq),
        "Reading": ("question_type.reading.total", df_mcq),
        "State Change": ("detect.state_change.total", df_mcq),
        "Ambiguity": ("hallucination_type.type_a.total", df_mcq),
        "Hallucination": ("hallucination_type.type_b.total", df_mcq),
    }
    result_data: dict[str, list[float]] = {c: [] for c in [*list(caps.keys()), "Average"]}

    for name in all_models:
        vals = []
        for cap, (pre, df) in caps.items():
            res = calculate_metric_value(get_model_data(df, name, model_col), [pre])
            result_data[cap].append(res[0] if res else np.nan)
            if res:
                vals.append(res)
        result_data["Average"].append(calculate_overall_average(vals))

    return pd.DataFrame(result_data, index=pd.Index(all_models, name="model"))


def generate_grounding_by_module(
    task_name: str, base_path: Path, model_col: str = "model_full_name"
) -> pd.DataFrame:
    """Generate grounding tables by module."""
    df = load_task_data(task_name, base_path)
    if task_name != "defuser-grounding-coordinates":
        df = filter_exclude_models(df, model_col)

    all_models = sorted(df[model_col].unique())
    s_map, m_map = extract_module_columns(df)
    sorted_s = sorted(s_map.keys())

    cols = sorted_s + (["Multi-Module Average"] if m_map else []) + ["Average"]
    result_data: dict[str, list[float]] = {c: [] for c in cols}

    for name in all_models:
        vals, m_data = [], get_model_data(df, name, model_col)
        for mod in sorted_s:
            res = calculate_metric_value(m_data, [f"module.{v}" for v in s_map[mod]])
            result_data[mod].append(res[0] if res else np.nan)
            if res:
                vals.append(res)
        if m_map:
            counts, trues = 0.0, 0.0
            for variants in m_map.values():
                res_m = calculate_metric_value(m_data, [f"module.{v}" for v in variants])
                if res_m:
                    trues += res_m[0] * res_m[1]
                    counts += res_m[1]
            avg_m = (trues / counts, counts) if counts > 0 else None
            result_data["Multi-Module Average"].append(avg_m[0] if avg_m else np.nan)
            if avg_m:
                vals.append(avg_m)
        result_data["Average"].append(calculate_overall_average(vals))

    return pd.DataFrame(result_data, index=pd.Index(all_models, name="model"))


def generate_grounding_by_capability(
    task_name: str, base_path: Path, model_col: str = "model_full_name"
) -> pd.DataFrame:
    """Generate grounding tables by capability."""
    df = load_task_data(task_name, base_path)
    if task_name != "defuser-grounding-coordinates":
        df = filter_exclude_models(df, model_col)

    caps = {
        "Color": "question_type.color.total",
        "Counting": "question_type.counting.total",
        "Element": "question_type.recognition.total",
        "Position": "question_type.position.total",
        "Reading": "question_type.reading.total",
        "Ambiguity": "hallucination_type.type_a.total",
        "Hallucination": "hallucination_type.type_b.total",
    }
    all_models = sorted(df[model_col].unique())
    result_data: dict[str, list[float]] = {c: [] for c in [*list(caps.keys()), "Average"]}

    for name in all_models:
        vals, m_data = [], get_model_data(df, name, model_col)
        for cap, pre in caps.items():
            res = calculate_metric_value(m_data, [pre])
            result_data[cap].append(res[0] if res else np.nan)
            if res:
                vals.append(res)
        result_data["Average"].append(calculate_overall_average(vals))

    return pd.DataFrame(result_data, index=pd.Index(all_models, name="model"))


def generate_aux_by_task_category(
    base_path: Path, model_col: str = "model_full_name"
) -> pd.DataFrame:
    """Collate latency and token usage aggregated by task category."""
    logger.info("generating_table", table="aux_by_task_category")

    categories = {
        "Manual VQA": ["expert-ocr", "expert-element-grounding", "expert-vqa"],
        "Simulator VQA": ["defuser-vqa-mcq", "defuser-vqa-oe"],
        "Simulator Localization": ["defuser-grounding-som", "defuser-grounding-coordinates"],
    }

    metrics = {"Latency": "model_latency.mean", "Tokens": "output.usage.output_tokens.mean"}

    all_task_names = [t for tasks in categories.values() for t in tasks]
    dfs = {t: filter_exclude_models(load_task_data(t, base_path)) for t in all_task_names}

    # Load Prediction DFs for Errors
    dfs_preds = {}
    for t in all_task_names:
        df_p = filter_exclude_models(load_predictions_data(t, base_path))
        if not df_p.empty and "prediction.error" in df_p.columns:
            dfs_preds[t] = df_p

    all_models = collect_all_models(list(dfs.values()), model_col)

    result_cols = []
    for cat in categories:
        result_cols.extend([f"{cat}_Lat", f"{cat}_Tok", f"{cat}_Err"])

    result_data: dict[str, list[float]] = {c: [] for c in result_cols}

    for model in all_models:
        for cat, tasks in categories.items():
            cat_lats, cat_toks = [], []
            cat_err_preds = 0.0
            cat_total_preds = 0.0

            for t in tasks:
                # 1. Get Latency/Tokens from Summary
                m_data = get_model_data(dfs[t], model, model_col)
                if not m_data.empty:
                    if metrics["Latency"] in m_data.columns:
                        val = float(m_data[metrics["Latency"]].to_numpy()[0])
                        if not pd.isna(val):
                            cat_lats.append(val * 1000)  # Convert to ms

                    if metrics["Tokens"] in m_data.columns:
                        val = float(m_data[metrics["Tokens"]].to_numpy()[0])
                        if not pd.isna(val):
                            cat_toks.append(val)

                # 2. Get Errors from Predictions
                if t in dfs_preds:
                    m_pred = get_model_data(dfs_preds[t], model, model_col)
                    if not m_pred.empty:
                        cat_total_preds += len(m_pred)
                        err_series = m_pred["prediction.error"]
                        bad_preds = (
                            err_series.dropna()
                            .apply(lambda x: "max_tokens_exceeded" in str(x))
                            .sum()
                        )
                        cat_err_preds += bad_preds

            result_data[f"{cat}_Lat"].append(np.mean(cat_lats) if cat_lats else np.nan)
            result_data[f"{cat}_Tok"].append(np.mean(cat_toks) if cat_toks else np.nan)

            if cat_total_preds > 0:
                result_data[f"{cat}_Err"].append((cat_err_preds / cat_total_preds) * 100)
            else:
                result_data[f"{cat}_Err"].append(np.nan)

    return pd.DataFrame(result_data, index=pd.Index(all_models, name="model"))


def _find_target_column(df: pd.DataFrame, metric_key: str) -> str | None:
    """Identify the target column in the dataframe based on the metric key."""
    if metric_key in df.columns:
        return metric_key

    suffix = metric_key.split(".")[-1] if "." in metric_key else metric_key
    if "tokens" in suffix:
        for col in df.columns:
            if "output_tokens" in col:
                return col
    elif "latency" in suffix:
        for col in df.columns:
            if "latency" in col:
                return col
    return None


def generate_aux_by_module_from_predictions(
    tasks: list[str], base_path: Path, metric_key: str, model_col: str = "model_full_name"
) -> pd.DataFrame:
    """Generate aux table by aggregating raw predictions (since modules are not columns)."""
    logger.info("generating_aux_from_predictions", metric=metric_key)
    all_rows = []

    is_latency = "latency" in metric_key
    is_error = "error" in metric_key

    for task in tasks:
        df_pred = filter_exclude_models(load_predictions_data(task, base_path))
        if df_pred.empty:
            continue

        if "example.module" not in df_pred.columns:
            logger.info("skip_task_no_module_col", task=task)
            continue

        target_col = None
        if is_error:
            if "prediction.error" in df_pred.columns:
                target_col = "prediction.error"
        else:
            target_col = _find_target_column(df_pred, metric_key)

        if not target_col:
            if "defuser" in task and not is_error:
                logger.warning(
                    "missing_metric_col",
                    task=task,
                    metric=metric_key,
                    available=list(df_pred.columns),
                )
            continue

        logger.info("found_metric_col", task=task, col=target_col)

        subset = df_pred[[model_col, "example.module", target_col]].copy()
        subset.columns = ["model", "module", "value"]

        if is_latency:
            subset["value"] = subset["value"] * 1000
        elif is_error:
            # STRICT CHECK: Only check for max_tokens_exceeded string
            subset["value"] = subset["value"].apply(
                lambda x: 1.0 if pd.notna(x) and "max_tokens_exceeded" in str(x) else 0.0
            )

        # Normalize module names
        subset["module"] = subset["module"].apply(normalize_module_name)
        # Apply Bucketing Logic: Convert any hyphenated module to 'Multi'
        subset.loc[subset["module"].str.contains("-"), "module"] = "Multi"

        all_rows.append(subset)

    if not all_rows:
        return pd.DataFrame()

    combined = pd.concat(all_rows, ignore_index=True)
    grouped = combined.groupby(["model", "module"])["value"].mean().unstack()

    if is_error:
        grouped = grouped * 100

    return cast("pd.DataFrame", grouped)


def format_latex_value(value: float) -> str:
    """Format a value for LaTeX table display."""
    if pd.isna(value):
        return "—"
    return "0.0" if value == 0.0 else f"{value:.1f}"


def model_name_to_latex(model_name: str) -> str:
    """Convert model name to LaTeX format."""
    mapping = {
        "claude-sonnet-4-5": r"\anthropic~Claude 4.5-Sonnet",
        "gemini-3-flash-preview": r"\gemini~Gemini 3-Flash",
        "gpt-5.2": r"\openai~GPT-5.2",
        "qwen3vl": r"\qwen~Qwen3-VL",
        "internvl35": r"\internvl~InternVL 3.5",
    }
    return mapping.get(model_name, model_name)


def _generate_combined_module_table(
    latex: list[str],
    m_vqa: pd.DataFrame,
    s_vqa: pd.DataFrame,
    som: pd.DataFrame,
    module_order: list[str],
) -> None:
    """Generate the combined module accuracy table."""
    latex.append(r"\begin{table}[tbh]")
    latex.append(r"\centering\footnotesize\renewcommand{\arraystretch}{1.4}")
    latex.append(r"\sisetup{table-format=2.1, uncertainty-mode = separate}")
    latex.append(r"\caption{Model accuracy on static evaluation datasets.}")
    latex.append(r"\label{tab:statics-per-module}")
    latex.append(r"\begin{tabular}{@{}p{3.0mm}  l *{14}{S} S @{}}")
    latex.append(r"\toprule")
    latex.append(
        r"& Model & {\wiresheading} & {\buttonheading} & {\keypadheading} & {\simonsaysheading} & {\whosonfirstheading} & {\memoryheading} & {\morsecodeheading} & {\complicatedwiresheading} & {\wiresequenceheading} & {\mazeheading} & {\passwordsheading} & {\strikesheading} & {\widgetsheading} & {Multi} & {Avg.}\\"
    )
    latex.append(r"\midrule")

    sections = [
        (r"Manual\\VQA", m_vqa),
        (r"Simulator\\VQA", s_vqa),
        (r"Simulator\\Localization", som),
    ]

    for label, df in sections:
        prefix = rf"\parbox[t]{{2mm}}{{\multirow{{5}} {{*}} {{\rotatebox[origin=c]{{90}}{{\textbf{{\textls[25]{{\shortstack{{{label}}}}}}}}}}}}}"
        for i, model in enumerate(df.index):
            row = [model_name_to_latex(str(model))]
            for mod in module_order:
                val = df.loc[model, mod] * 100 if mod in df.columns else np.nan
                row.append(format_latex_value(val))
            m_val = (
                df.loc[model, "Multi-Module Average"] * 100
                if "Multi-Module Average" in df.columns
                else np.nan
            )
            row.append(format_latex_value(m_val))
            row.append(format_latex_value(df.loc[model, "Average"] * 100))

            # Proper list construction
            row_items = row
            full_row = [prefix, *row_items] if i == 0 else ["", *row_items]

            latex.append(" & ".join(full_row) + r" \\")
        latex.append(r"\midrule")

    latex[-1] = r"\bottomrule"
    latex.append(r"\end{tabular}\end{table}" + "\n")


def _generate_capability_table(
    latex: list[str],
    df: pd.DataFrame,
    caption: str,
    label: str,
    cols: list[str],
    col_spec: str,
    header_row: str,
) -> None:
    """Generate a standard capability breakdown table."""
    latex.append(r"\begin{table}[tbh]\centering\footnotesize\renewcommand{\arraystretch}{1.4}")
    latex.append(r"\sisetup{table-format=2.1, uncertainty-mode = separate}")
    latex.append(rf"\caption{{{caption}}}")
    latex.append(rf"\label{{{label}}}")
    latex.append(rf"\begin{{tabular}}{{{col_spec}}}\toprule")
    latex.append(f"{header_row} \\\\ \\midrule")

    for model in df.index:
        row = [model_name_to_latex(str(model))]
        for col in cols:
            val = df.loc[model, col] * 100 if col in df.columns else np.nan
            row.append(format_latex_value(val))
        latex.append(f"{' & '.join(row)} \\\\")
    latex.append(r"\bottomrule\end{tabular}\end{table}" + "\n")


def _generate_localization_comparison_table(
    latex: list[str], coords: pd.DataFrame, som: pd.DataFrame, loc_order: list[str]
) -> None:
    """Generate the Coordinates vs SoM comparison table."""
    latex.append(r"\begin{table}[tbh]\centering\footnotesize\renewcommand{\arraystretch}{1.4}")
    latex.append(r"\sisetup{table-format=2.1, uncertainty-mode = separate}")
    latex.append(r"\caption{Comparison of localization formats.}")
    latex.append(r"\label{tab:localization-coordinates-vs-som}")
    # Fix: One single backslash for newline
    latex.append(r"\begin{tabular}{@{}p{3.0mm} l *{11}{S} S @{}}\toprule")
    latex.append(
        r"& Model & {\wiresheading} & {\buttonheading} & {\keypadheading} & {\simonsaysheading} & {\whosonfirstheading} & {\memoryheading} & {\morsecodeheading} & {\complicatedwiresheading} & {\wiresequenceheading} & {\mazeheading} & {\passwordsheading} & {Avg.}\\ \midrule"
    )

    for label, df in [("Coordinates", coords), ("Set-of-Marks", som)]:
        prefix = rf"\parbox[t]{{2mm}}{{\multirow{{5}} {{*}} {{\rotatebox[origin=c]{{90}}{{\textbf{{\textls[25]{{{label}}}}}}}}}}}"
        for i, model in enumerate(df.index):
            row = [model_name_to_latex(str(model))]
            for mod in loc_order:
                val = df.loc[model, mod] * 100 if mod in df.columns else np.nan
                row.append(format_latex_value(val))
            row.append(format_latex_value(df.loc[model, "Average"] * 100))

            row_items = row
            full_row = [prefix, *row_items] if i == 0 else ["", *row_items]

            latex.append(" & ".join(full_row) + r" \\")
        latex.append(r"\midrule")

    latex[-1] = r"\bottomrule"
    latex.append(r"\end{tabular}\end{table}" + "\n")


def _generate_aux_table(
    latex: list[str],
    df: pd.DataFrame,
    caption: str,
    label: str,
    module_order: list[str],
    fmt: str = "1.2",
    avg_fmt: str = "1.2",
) -> None:
    """Generate an auxiliary table (latency/tokens)."""
    # Fix: Increased tabcolsep to 4.5pt for wider tables
    latex.append(
        rf"\begin{{table}}[tbh]\centering\footnotesize\renewcommand{{\arraystretch}}{{1.4}}\setlength{{\tabcolsep}}{{4.5pt}}\caption{{{caption}}}\label{{{label}}}"
    )
    # *{15} covers 13 modules + Multi + Avg
    latex.append(rf"\begin{{tabular}}{{l *{{15}}{{S[table-format={fmt}]}}}}\toprule")
    latex.append(
        r"Model & {\wiresheading} & {\buttonheading} & {\keypadheading} & {\simonsaysheading} & {\whosonfirstheading} & {\memoryheading} & {\morsecodeheading} & {\complicatedwiresheading} & {\wiresequenceheading} & {\mazeheading} & {\passwordsheading} & {\strikesheading} & {\widgetsheading} & {Multi} & {Avg.} \\ \midrule"
    )

    for model in df.index:
        row = [model_name_to_latex(str(model))]
        row_vals = []
        for mod in module_order:
            val = df.loc[model, mod] if mod in df.columns else np.nan
            if not pd.isna(val):
                row_vals.append(val)
            row.append(f"{val:{'.0f' if '0' in fmt else '.1f'}}" if not pd.isna(val) else "—")

        # Multi Column
        val_multi = df.loc[model, "Multi"] if "Multi" in df.columns else np.nan
        if not pd.isna(val_multi):
            row_vals.append(val_multi)
        row.append(
            f"{val_multi:{'.0f' if '0' in fmt else '.1f'}}" if not pd.isna(val_multi) else "—"
        )

        row_avg = np.nanmean(row_vals) if row_vals else np.nan
        row.append(
            f"{row_avg:{'.0f' if '0' in avg_fmt else '.1f'}}" if not pd.isna(row_avg) else "—"
        )

        latex.append(f"{' & '.join(row)} \\\\")
    latex.append(r"\bottomrule\end{tabular}\end{table}")


def generate_latex_tables(output_path: Path) -> None:
    """Generate LaTeX tables from CSV data with specific academic formatting."""
    desired = ["claude-sonnet-4-5", "gemini-3-flash-preview", "gpt-5.2", "qwen3vl", "internvl35"]

    def load_filtered(name: str) -> pd.DataFrame:
        csv_path = output_path / f"{name}.csv"
        if not csv_path.exists():
            logger.warning("csv_not_found", path=str(csv_path))
            return pd.DataFrame()
        df = pd.read_csv(csv_path, index_col=0)
        return cast("pd.DataFrame", df.reindex([m for m in desired if m in df.index]))

    m_vqa = load_filtered("manual_vqa_by_module")
    s_vqa = load_filtered("simulator_vqa_by_module")
    som = load_filtered("simulator_grounding_som_by_module")
    coords = load_filtered("simulator_grounding_coordinates_by_module")
    m_cap = load_filtered("manual_vqa_by_capability")
    s_cap = load_filtered("simulator_vqa_by_capability")
    c_cap = load_filtered("simulator_grounding_coordinates_by_capability")

    # Aux tables
    aux_task = load_filtered("aux_by_task_category")
    aux_lat = load_filtered("aux_module_latency")
    aux_tok = load_filtered("aux_module_tokens")
    aux_err = load_filtered("aux_module_errors")

    module_order = [
        "WIRES",
        "BUTTON",
        "KEYPAD",
        "SIMON",
        "WHOSONFIRST",
        "MEMORY",
        "MORSECODE",
        "VENN",
        "WIRESEQUENCE",
        "MAZE",
        "PASSWORD",
        "STRIKES",
        "WIDGET",
    ]
    latex = []

    _generate_combined_module_table(latex, m_vqa, s_vqa, som, module_order)

    _generate_capability_table(
        latex,
        m_cap,
        "Manual VQA accuracy breakdown by capability.",
        "tab:expert-statics-capabilities",
        [
            "Reading",
            "Element Grounding",
            "Procedural Reasoning",
            "Ambiguity",
            "Hallucination",
            "Average",
        ],
        "l *{5}{S} S @{}",
        r"Model & {Reading} & {Element Grounding} & {Procedural Reasoning} & {Ambiguity} & {Hallucination} & {Avg.}",
    )

    _generate_capability_table(
        latex,
        s_cap,
        "Simulator VQA accuracy breakdown per capability.",
        "tab:defuser-statics-vqa-capabilities",
        [
            "Color",
            "Counting",
            "Describing",
            "Indexing",
            "Reading",
            "State Change",
            "Ambiguity",
            "Hallucination",
            "Average",
        ],
        "l *{8}{S} S @{}",
        r"Model & {Color} & {Counting} & {Describing} & {Indexing} & {Reading} & {State Change} & {Ambiguity} & {Hallucination} & {Avg.}",
    )

    _generate_capability_table(
        latex,
        c_cap,
        "Simulator localization accuracy breakdown per capability.",
        "tab:defuser-statics-localization-capabilities",
        [
            "Color",
            "Counting",
            "Element",
            "Position",
            "Reading",
            "Ambiguity",
            "Hallucination",
            "Average",
        ],
        "l *{7}{S} S @{}",
        r"Model & {Color} & {Counting} & {Element} & {Position} & {Reading} & {Ambiguity} & {Hallucination} & {Avg.}",
    )

    _generate_localization_comparison_table(
        latex,
        coords,
        som,
        [
            "WIRES",
            "BUTTON",
            "KEYPAD",
            "SIMON",
            "WHOSONFIRST",
            "MEMORY",
            "MORSECODE",
            "VENN",
            "WIRESEQUENCE",
            "MAZE",
            "PASSWORD",
        ],
    )

    # Table 6: Aux Tasks
    # Fix: Added setlength tabcolsep 2.5pt to tighten this specific table
    latex.append(
        r"\begin{table}[tbh]\centering\footnotesize\renewcommand{\arraystretch}{1.4}\setlength{\tabcolsep}{2.5pt}\caption{Latency (ms), Token Usage, and Think Error \% by Task.}\label{tab:aux-task-stats}"
    )
    latex.append(r"\begin{tabular}{l *{9}{S[table-format=4.0]}}\toprule")
    latex.append(
        r"Model & \multicolumn{3}{c}{Manual VQA} & \multicolumn{3}{c}{Simulator VQA} & \multicolumn{3}{c}{Simulator Localization} \\ \cmidrule(lr){2-4} \cmidrule(lr){5-7} \cmidrule(lr){8-10} & {\textbf{Latency}} & {\textbf{Tokens}} & {\textbf{Think Error \%}} & {\textbf{Latency}} & {\textbf{Tokens}} & {\textbf{Think Error \%}} & {\textbf{Latency}} & {\textbf{Tokens}} & {\textbf{Think Error \%}} \\ \midrule"
    )
    categories = ["Manual VQA", "Simulator VQA", "Simulator Localization"]
    for model in aux_task.index:
        row = [model_name_to_latex(str(model))]
        for cat in categories:
            lat = aux_task.loc[model, f"{cat}_Lat"]
            tok = aux_task.loc[model, f"{cat}_Tok"]
            err = aux_task.loc[model, f"{cat}_Err"]
            row.append(f"{lat:.0f}" if not pd.isna(lat) else "—")
            row.append(f"{tok:.0f}" if not pd.isna(tok) else "—")
            row.append(f"{err:.1f}" if not pd.isna(err) else "0.0")
        latex.append(f"{' & '.join(row)} \\\\")
    latex.append(r"\bottomrule\end{tabular}\end{table}" + "\n")

    _generate_aux_table(
        latex,
        aux_lat,
        "Mean model latency (ms) per game module.",
        "tab:aux-latency",
        module_order,
        fmt="3.0",
        avg_fmt="3.0",
    )
    _generate_aux_table(
        latex,
        aux_tok,
        "Mean output tokens generated per game module.",
        "tab:aux-tokens",
        module_order,
        fmt="3.0",
        avg_fmt="3.0",
    )
    _generate_aux_table(
        latex,
        aux_err,
        "Mean think error percentage per game module.",
        "tab:aux-errors",
        module_order,
        fmt="2.1",
        avg_fmt="2.1",
    )

    (output_path / "tables.tex").write_text("\n".join(latex), encoding="utf-8")


def main() -> None:
    """Main function to generate all tables."""
    base_path, out_path = Path("storage/outputs"), Path("storage/outputs/statics_results_tables")
    out_path.mkdir(parents=True, exist_ok=True)

    tasks = [
        "expert-ocr",
        "expert-element-grounding",
        "expert-vqa",
        "defuser-vqa-mcq",
        "defuser-vqa-oe",
        "defuser-grounding-som",
        "defuser-grounding-coordinates",
    ]

    try:
        generate_manual_vqa_by_module(
            ["expert-ocr", "expert-element-grounding", "expert-vqa"], base_path
        ).to_csv(out_path / "manual_vqa_by_module.csv")
        generate_manual_vqa_by_capability(base_path).to_csv(
            out_path / "manual_vqa_by_capability.csv"
        )
        generate_simulator_vqa_by_module(base_path).to_csv(
            out_path / "simulator_vqa_by_module.csv"
        )
        generate_simulator_vqa_by_capability(base_path).to_csv(
            out_path / "simulator_vqa_by_capability.csv"
        )
        generate_grounding_by_module("defuser-grounding-som", base_path).to_csv(
            out_path / "simulator_grounding_som_by_module.csv"
        )
        generate_grounding_by_capability("defuser-grounding-som", base_path).to_csv(
            out_path / "simulator_grounding_som_by_capability.csv"
        )
        generate_grounding_by_module("defuser-grounding-coordinates", base_path).to_csv(
            out_path / "simulator_grounding_coordinates_by_module.csv"
        )
        generate_grounding_by_capability("defuser-grounding-coordinates", base_path).to_csv(
            out_path / "simulator_grounding_coordinates_by_capability.csv"
        )

        # New Auxiliary Tables - from raw predictions
        generate_aux_by_task_category(base_path, "model_full_name").to_csv(
            out_path / "aux_by_task_category.csv"
        )
        generate_aux_by_module_from_predictions(tasks, base_path, "latency").to_csv(
            out_path / "aux_module_latency.csv"
        )
        generate_aux_by_module_from_predictions(
            tasks, base_path, "output.usage.output_tokens"
        ).to_csv(out_path / "aux_module_tokens.csv")
        generate_aux_by_module_from_predictions(tasks, base_path, "prediction.error").to_csv(
            out_path / "aux_module_errors.csv"
        )

        generate_latex_tables(out_path)
        logger.info("all_tables_generated")
    except (DataLoadError, TableGenerationError) as e:
        logger.exception("generation_failed", error=str(e))


if __name__ == "__main__":
    main()
