"""The `CheckResult` type, its renderer and format emitters, and `gptnt doctor`'s environment
probes (players, services, game, machine, validation).
"""

from gptnt.cli.checks.formats import Report
from gptnt.cli.checks.render import render_report
from gptnt.cli.checks.result import CheckResult, CheckStatus

__all__ = ["CheckResult", "CheckStatus", "Report", "render_report"]
