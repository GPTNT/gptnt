"""The shared findings framework: the `CheckResult` value object, the section renderer, and the
CI-format emitters — plus doctor's environment/readiness probes, split by concern (players,
services, game, machine, validation).

Every findings command depends outward on this leaf; nothing here reaches into a feature package.
"""

from gptnt.cli.checks.formats import Report
from gptnt.cli.checks.render import render_report
from gptnt.cli.checks.result import CheckResult, CheckStatus

__all__ = ["CheckResult", "CheckStatus", "Report", "render_report"]
