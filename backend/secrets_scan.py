"""Secrets and PII scanner.

Regex rules for common credentials, connection URLs, and password assignments.
"""
import re

_K = r"[A-Za-z0-9_-]"
_NOT_K = r"(?![A-Za-z0-9_-])"

# A sensitive word as its own identifier segment. DB_PASSWORD, client_secret, and
# AWS_SECRET_ACCESS_KEY match. "secretary" and "password policy" do not.
_SENSITIVE_KEY = re.compile(
    r"(?i)(?:^|[_-])"
    r"(?:password|passwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token|"
    r"private[_-]?key(?:[_-]?id)?)(?:$|[_-])"
)
_MIN_SECRET = 6
_MASK = re.compile(r"(?i)^(?:x+|\*+)$")
_INTERP = re.compile(
    r"^(?:\$\{[^{}]+\}|\$[A-Za-z_][A-Za-z0-9_]*|\{\{[^{}]+\}\}|%[A-Za-z_][A-Za-z0-9_]*%|<[^>\n]{1,80}>)$"
)
_PLACEHOLDER_WORD = re.compile(
    r"(?i)^(?:"
    r"change[-_]?me|"
    r"examples?(?:[-_]?(?:key|secret|password|token|[0-9]{1,8}))?|"
    r"null|none|nil|undefined|todo|fixme|placeholder|dummy|redacted|sample|"
    r"password|passwd|secret|"
    r"your[-_][a-z0-9_-]*here"
    r")$"
)

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
    # User may be empty (redis://:pass@host). Password is group "value" so placeholders can be dropped.
    "db_url_password": re.compile(
        r"\b(?:(?i:postgresql|postgres|mysql|mongodb(?:\+srv)?|rediss|redis|amqps|amqp|"
        r"mssql(?:\+[A-Za-z]+)?|sqlserver))://[^\s:/@'\"]*:(?P<value>[^\s@/'\"]+)@[\w.-]+(?::\d+)?"
    ),
    "private_key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    # .env and config assignments, quoted or not, with an optional export. Placeholders are
    # filtered in scan(); the span stays the whole assignment, which is what redact() replaces.
    "password_assignment": re.compile(
        r"(?i)(?<![A-Za-z0-9_])"
        r"(?:export[ \t]+)?"
        r"[\"']?"
        r"(?P<key>[A-Za-z_][A-Za-z0-9_-]{0,80})"
        r"[\"']?"
        r"[ \t]*[:=][ \t]*"
        r"(?P<value>\"[^\"\n]{0,200}\"|'[^'\n]{0,200}'|[^\s\"'#,;)]{1,200})"
    ),
}


GENERIC = {"password_assignment"}  # catch-all rules that yield to specific credential rules


def _strip_value(raw: str) -> tuple[str, bool]:
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        return raw[1:-1].strip(), True
    return raw, False


def _is_placeholder(value: str) -> bool:
    """Blanks, short strings, interpolations, and stand-in words are not credentials."""
    if len(value) < _MIN_SECRET or any(c.isspace() for c in value):
        return True
    if re.search(r"[()\[\]{}]", value):
        return True
    if _MASK.fullmatch(value) or len(set(value)) == 1:
        return True
    return bool(_PLACEHOLDER_WORD.fullmatch(value) or _INTERP.fullmatch(value))


def _looks_like_secret(value: str, quoted: bool = False) -> bool:
    """A pasted secret has a digit or a base64 symbol, or it is at least 16 characters.

    Quoted values of 8 or more characters still count, which keeps the old
    quoted-password behavior, after placeholders have been removed.
    """
    if _is_placeholder(value):
        return False
    if re.search(r"\d", value) or re.search(r"[+/=]", value):
        return True
    # Long enough that it is not a single ordinary word. "rotate" stays quiet.
    if len(value) >= 16:
        return True
    return bool(quoted and len(value) >= 8)


def _keep_match(name: str, m: re.Match) -> bool:
    if name == "password_assignment":
        key = m.group("key") or ""
        if not _SENSITIVE_KEY.search(key):
            return False
        value, quoted = _strip_value(m.group("value") or "")
        return _looks_like_secret(value, quoted)
    if name == "db_url_password":
        value, quoted = _strip_value(m.group("value") or "")
        return _looks_like_secret(value, quoted)
    return True


def scan(text: str) -> list[dict]:
    """Return non-overlapping findings. A specific credential rule always beats the generic
    password_assignment rule on overlap (so api_key="sk-ant-..." reports anthropic_key and blocks);
    otherwise the longest span wins, ties going to the rule defined first.
    Placeholder assignment values are dropped before that."""
    cands = []
    for order, (name, rx) in enumerate(RULES.items()):
        for m in rx.finditer(text):
            if not _keep_match(name, m):
                continue
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
