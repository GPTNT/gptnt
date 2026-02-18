from pathlib import Path

import pandas as pd
import structlog
from huggingface_hub import HfApi

structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ]
)

logger = structlog.get_logger()

PROJECTS = [
    # "defuser-grounding-coordinates",
    # "defuser-grounding-som",
    "defuser-vqa-oe"
    # "defuser-vqa-mcq",
    # "expert-vqa",
    # "expert-ocr",
    # "expert-element-grounding",
]

ORG = "GPTNT"
BASE_DIR = Path("storage/outputs")


def clean_weave_list_string(val):
    """Removes 'WeaveList(' prefix and ')' suffix from strings.

    Example: "WeaveList(['a', 'b'])" -> "['a', 'b']"
    """
    if isinstance(val, str) and val.startswith("WeaveList(") and val.endswith(")"):
        return val[10:-1]
    return val


def process_csv_for_upload(file_path: Path) -> Path:
    """Reads the CSV, cleans WeaveList wrappers, saves a temporary file, and returns the path to
    the cleaned file."""
    df = pd.read_csv(file_path, low_memory=False)

    # Apply cleaning to all object (string) columns
    # We use applymap (or map in pandas 2.1+) to handle element-wise transformation safely
    # Checking column types first is more efficient
    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].apply(clean_weave_list_string)

    # Create a temporary path for the cleaned file
    clean_path = file_path.with_name(f"clean_{file_path.name}")
    df.to_csv(clean_path, index=False)

    return clean_path


def upload_to_hf(project_name: str, api: HfApi) -> None:
    """Upload the combined predictions CSV to Hugging Face as a dataset."""
    folder_name = f"{project_name}_results"
    original_csv_path = BASE_DIR / folder_name / "predictions" / "all_models_predictions.csv"
    repo_id = f"{ORG}/{folder_name}"

    log = logger.bind(project=project_name, repo_id=repo_id)

    if not original_csv_path.exists():
        log.warning("upload_skipped", reason="file_not_found", path=str(original_csv_path))
        return

    log.info("processing_file")

    try:
        # Clean the file and get path to the cleaned version
        csv_to_upload = process_csv_for_upload(original_csv_path)

        log.info("upload_starting")

        api.create_repo(repo_id=repo_id, repo_type="dataset", exist_ok=True)

        api.upload_file(
            path_or_fileobj=str(csv_to_upload),
            path_in_repo="all_models_predictions.csv",
            repo_id=repo_id,
            repo_type="dataset",
            commit_message=f"Upload latest predictions for {project_name}",
        )

        log.info("upload_successful")

        # Cleanup the temporary file
        csv_to_upload.unlink()

    except Exception as e:
        log.exception("processing_or_upload_failed", error=str(e))
        # Attempt to cleanup if the file was created but upload failed
        clean_file = original_csv_path.with_name(f"clean_{original_csv_path.name}")
        if clean_file.exists():
            clean_file.unlink()
        raise


def main() -> None:
    """Initialize API and process all project uploads."""
    api = HfApi()
    logger.info("starting_hf_upload_process", count=len(PROJECTS))

    for project in PROJECTS:
        try:
            upload_to_hf(project, api)
        except Exception as e:
            logger.exception("upload_failed_final", project=project, error=str(e))


if __name__ == "__main__":
    main()
