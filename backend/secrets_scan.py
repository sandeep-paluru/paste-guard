"""Secrets and PII scanner..

Regex rules for common credentials and password assignments.
"""
import re

RULES = {
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "github_token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    "openai_key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "slack_token": re.compile(r"\bxox[abpors]-[A-Za-z0-9-]{10,}\b"),
    "private_key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "password_assignment": re.compile(r"(?i)\b(password|passwd|secret|api_key)\s*[:=]\s*['\"][^'\"]{6,}['\"]"),
}


def scan(text: str) -> list[dict]:
    findings = []
    for name, rx in RULES.items():
        for m in rx.finditer(text):
            findings.append({"type": name, "start": m.start(), "end": m.end()})
    return findings


def redact(text: str, findings: list[dict]) -> str:
    for f in sorted(findings, key=lambda f: f["start"], reverse=True):
        text = text[: f["start"]] + f"[REDACTED:{f['type']}]" + text[f["end"]:]
    return text


# Soft markers that a document is internal. Used as a coach signal by the
# backend and as part of the regex baseline in eval/run_eval.py.
MARKERS = re.compile(
    r"(?i)\b(confidential|strictly private|internal only|internal use only|proprietary|do not distribute|"
    r"not for distribution|attorney[- ]client privileged|trade secret|restricted)\b")


def markers(text: str) -> list[dict]:
    return [{"type": "confidential_marker", "start": m.start(), "end": m.end(), "match": m.group(0)}
            for m in MARKERS.finditer(text)]
