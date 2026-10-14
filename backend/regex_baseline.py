"""Regex and keyword DLP baseline: the comparison point in eval/ and on the /demo/compare page.

Lives in backend/ so the server can import it; eval/baseline.py re-exports it for the eval scripts."""
import re

import secrets_scan

# Baseline: what a typical regex DLP rule set catches. Secrets rules, explicit
# classification markers, and a dictionary of sensitive business keywords.
KEYWORDS = re.compile(
    r"(?i)\b(confidential|proprietary|internal only|internal use only|do not distribute|trade secret|"
    r"privileged|restricted|not for distribution|board of directors|term sheet|acquisition|layoff|"
    r"reduction in force|compensation band|salary band|settlement|incident postmortem|roadmap)\b")


def regex_reasons(text: str) -> list[str]:
    """What the baseline matched, e.g. ["secret: aws_access_key", "keyword: confidential"]. Empty list = no flag."""
    out = [f"secret: {f['type']}" for f in secrets_scan.scan(text)] + [f"marker: {m['type']}" for m in secrets_scan.markers(text)]
    out += sorted({f"keyword: {m.group(0).lower()}" for m in KEYWORDS.finditer(text)})
    return out


def regex_flag(text: str) -> bool:
    return bool(secrets_scan.scan(text) or secrets_scan.markers(text) or KEYWORDS.search(text))
