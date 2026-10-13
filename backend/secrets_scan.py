"""Secrets and PII scanner. Day 1: a few regex rules.

TODO(day 3): add entropy checks, more providers, and PII rules
(emails, phone numbers, names) tuned on BigCode PII and ai4privacy.
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
