import structlog
import wandb
from tqdm import tqdm

WANDB_PATH = "gptnt/dont-stop-believin"
logger = structlog.get_logger()
api = wandb.Api()

runs = api.runs(WANDB_PATH)
logger.info(f"Total runs found: {len(runs)}")

for run in tqdm(runs, desc="Processing runs", total=len(runs)):
    run.config["attempt"] = 1
    run.config["attempt_name"] = f"{run.config['experiment_name']}_attempt1"
    run.update()
