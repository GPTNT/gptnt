import os
import subprocess
import sys
from importlib.util import find_spec


def run_streamlit_app() -> None:
    """Run the Streamlit app (using subprocess)."""
    spec = find_spec("gptnt.app.__main__")
    if spec is None or spec.origin is None:
        raise RuntimeError("Could not locate gptnt.app.__main__")
    location = spec.origin
    command = [sys.executable, "-m", "streamlit", "run", str(location)]
    env_vars = {**os.environ.copy(), "STREAMLIT_THEME_BASE": "light"}
    _ = subprocess.run(command, check=True, env=env_vars)  # noqa: S603
