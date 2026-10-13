"""Regex and keyword DLP baseline shared by run_eval.py and bench_report.py."""
import re

import secrets_scan

# Baseline: what a typical regex DLP rule set catches. Secrets rules, explicit
# classification markers, and a dictionary of sensitive business keywords.
KEYWORDS = re.compile(
    r"(?i)\b(confidential|proprietary|internal only|internal use only|do not distribute|trade secret|"
    r"privileged|restricted|not for distribution|board of directors|term sheet|acquisition|layoff|"
    r"reduction in force|compensation band|salary band|settlement|incident postmortem|roadmap)\b")


def regex_flag(text: str) -> bool:
    return bool(secrets_scan.scan(text) or secrets_scan.markers(text) or KEYWORDS.search(text))
