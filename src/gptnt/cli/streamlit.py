import os
import subprocess
import sys
from pathlib import Path


def run_streamlit_app() -> None:
    """Run the Streamlit app (using subprocess)."""
    location = Path(__file__).parent.parent / "app" / "__main__.py"
    command = [sys.executable, "-m", "streamlit", "run", str(location)]
    env_vars = {**os.environ.copy(), "STREAMLIT_THEME_BASE": "light"}
    _ = subprocess.run(command, check=True, env=env_vars)  # noqa: S603
