"""The `gptnt doctor` host check: report machine specs (informational) and warn on low free disk.

Returns :class:`CheckResult` rows and never raises — host probing that fails degrades to a single
warn rather than aborting the report.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

import psutil

from gptnt.cli.checks.result import CheckResult
from gptnt.common.paths import Paths

paths = Paths()

DISK_WARN_GIB = 10.0


def _nearest_existing(path: Path) -> Path:
    """Walk up to the first existing ancestor (the output dir may not exist yet)."""
    for candidate in (path, *path.parents):
        if candidate.exists():
            return candidate
    return Path(path.anchor or ".")


def _detect_gpu() -> str | None:
    """First GPU name via `nvidia-smi` (Linux), or None when unavailable."""
    if sys.platform != "linux":
        return None
    try:
        completed = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    first_line = completed.stdout.strip().splitlines()
    return first_line[0].strip() if first_line else None


def check_machine() -> list[CheckResult]:
    """Report host specs + free disk; degrade to a single warn if probing the host fails."""
    try:
        return _collect_machine()
    except Exception as exc:  # noqa: BLE001 — purely informational; never abort the report
        return [CheckResult("Machine", "warn", "could not read host info", str(exc))]


def _collect_machine() -> list[CheckResult]:
    """Report host specs (informational) and warn on low free disk for experiment outputs."""
    ram_gib = psutil.virtual_memory().total / 1024**3
    cpus = os.cpu_count() or 0
    spec = f"{platform.system()} {platform.machine()}, {cpus} CPUs, {ram_gib:.1f} GiB RAM"
    gpu = _detect_gpu()
    if gpu:
        spec = f"{spec}, GPU: {gpu}"
    findings = [CheckResult("Machine", "pass", spec)]

    target = _nearest_existing(paths.experiment_recorder_dir)
    free_gib = shutil.disk_usage(target).free / 1024**3
    detail = f"{free_gib:.1f} GiB free on {target}"
    if free_gib < DISK_WARN_GIB:
        findings.append(
            CheckResult(
                "Disk space",
                "warn",
                detail,
                f"Below {DISK_WARN_GIB:.0f} GiB free; experiment recordings accumulate here.",
            )
        )
    else:
        findings.append(CheckResult("Disk space", "pass", detail))
    return findings
