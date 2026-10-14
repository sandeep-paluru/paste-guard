"""Secrets and PII scanner..

Regex rules for common credentials and password assignments.
"""
import re

_K = r"[A-Za-z0-9_-]"
_NOT_K = r"(?![A-Za-z0-9_-])"

RULES = {
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "aws_temp_key": re.compile(r"\bASIA[0-9A-Z]{16}\b"),
    "github_token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    "github_pat_fine_grained": re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}" + _NOT_K),
    "anthropic_key": re.compile(r"(?<![A-Za-z0-9_-])sk-ant-[a-z]+\d{2}-" + _K + r"{20,}" + _NOT_K),
    "openai_key": re.compile(
        r"(?<![A-Za-z0-9_-])sk-(?!ant-)(?:proj-|svcacct-|admin-)?" + _K + r"{20,}" + _NOT_K),
    "xai_key": re.compile(r"\bxai-[A-Za-z0-9]{40,}\b"),
    "google_api_key": re.compile(r"\bAIza[0-9A-Za-z_-]{35}" + _NOT_K),
    "google_oauth_client_secret": re.compile(r"\bGOCSPX-[A-Za-z0-9_-]{28}" + _NOT_K),
    "stripe_key": re.compile(r"\b[sr]k_(?:live|test)_[0-9A-Za-z]{16,}\b"),
    "slack_token": re.compile(r"\bxox[abpors]-[A-Za-z0-9-]{10,}\b"),
    "slack_webhook": re.compile(
        r"https://hooks\.slack\.com/services/T[A-Z0-9]{8,}/B[A-Z0-9]{8,}/[A-Za-z0-9]{20,}"),
    "jwt": re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
    "huggingface_token": re.compile(r"\bhf_[A-Za-z0-9]{34,}\b"),
    "gitlab_token": re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}" + _NOT_K),
    "npm_token": re.compile(r"\bnpm_[A-Za-z0-9]{36}\b"),
    "sendgrid_key": re.compile(r"\bSG\.[A-Za-z0-9_-]{22}\.[A-Za-z0-9_-]{43}" + _NOT_K),
    "twilio_key": re.compile(r"\bSK[0-9a-fA-F]{32}\b"),
    "azure_storage_key": re.compile(r"\bAccountKey=[A-Za-z0-9+/]{40,}={0,2}"),
    "db_url_password": re.compile(
        r"\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?)://[^\s:/@'\"]+:[^\s@/'\"]+@[\w.-]+(?::\d+)?"),
    "private_key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "password_assignment": re.compile(r"(?i)\b(password|passwd|secret|api_key)\s*[:=]\s*['\"][^'\"]{6,}['\"]"),
}


GENERIC = {"password_assignment"}  # catch-all rules that yield to specific credential rules


def scan(text: str) -> list[dict]:
    """Return non-overlapping findings. A specific credential rule always beats the generic
    password_assignment rule on overlap (so api_key="sk-ant-..." reports anthropic_key and blocks);
    otherwise the longest span wins, ties going to the rule defined first."""
    cands = []
    for order, (name, rx) in enumerate(RULES.items()):
        for m in rx.finditer(text):
            cands.append((name in GENERIC, m.start() - m.end(), order, m.start(), m.end(), name))
    cands.sort()
    findings = []
    for _, _, _, start, end, name in cands:
        if all(end <= f["start"] or start >= f["end"] for f in findings):
            findings.append({"type": name, "start": start, "end": end})
    return sorted(findings, key=lambda f: f["start"])


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
