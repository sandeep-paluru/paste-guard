"""Secrets and PII scanner.

Regex rules for common credentials, connection URLs, and password assignments.
Known-safe values are filtered afterwards by apply_allowlist, so a documented
sample key can be ignored without changing what scan() detects.

`pasteguard scan` runs these rules on files or stdin. It does not load the
model, the index, or the server. `--format sarif` writes SARIF 2.1.0.
`--write-baseline` records fingerprints, and `--baseline` hides findings
already recorded there. `--staged` scans lines added in the index, reading
the staged blob. `--diff-base REF` scans lines added since the merge-base
of REF and HEAD. A secret on a line the diff did not add is left out.
`pasteguard:ignore` on a finding's first line, or `pasteguard:ignore-next-line`
on the line above, suppresses that finding. `--no-inline-ignore` turns the
markers off.

`[[scan.rules]]` in paste-guard.toml, and a TOML file passed with `--rules`,
add detectors. A custom rule has a name, a regex, and a severity (`block` or
`coach`). `keywords` is a case-insensitive substring prefilter: the regex runs
only on lines that contain one. `secret_group` picks the capture that is the
secret (default 0, the whole match). `min_entropy` is a Shannon floor, in bits
per character, on that capture. `description` is the SARIF text.

Custom rules are matched per line, and only the first 10000 characters of a
line are scanned. That bounds a runaway pattern to one line. A nested
quantifier can still be slow on a long line, so keep the regex specific.
They do not cross line boundaries. The server and the extension do not load
them; `scan()` without a ruleset is the built-in detectors only.
"""
import argparse
import fnmatch
import hashlib
import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from urllib.parse import quote

try:
    import tomllib
except ImportError:  # Python 3.10
    import tomli as tomllib

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

# JWTs and password assignments coach. Every other rule is a live credential and blocks.
COACH_RULES = frozenset({"jwt", "password_assignment"})

# One short SARIF description per detector. No sample values.
RULE_DESCRIPTIONS = {
    "aws_access_key": "AWS access key ID",
    "aws_temp_key": "AWS temporary access key ID",
    "github_token": "GitHub personal access token",
    "github_pat_fine_grained": "GitHub fine-grained personal access token",
    "anthropic_key": "Anthropic API key",
    "openai_key": "OpenAI API key",
    "xai_key": "xAI API key",
    "google_api_key": "Google API key",
    "google_oauth_client_secret": "Google OAuth client secret",
    "stripe_key": "Stripe secret or restricted key",
    "slack_token": "Slack token",
    "slack_webhook": "Slack incoming webhook URL",
    "jwt": "JSON Web Token",
    "huggingface_token": "Hugging Face access token",
    "gitlab_token": "GitLab personal access token",
    "npm_token": "npm access token",
    "sendgrid_key": "SendGrid API key",
    "twilio_key": "Twilio API key",
    "azure_storage_key": "Azure storage account key",
    "db_url_password": "Database URL with a password",
    "private_key": "PEM private key",
    "password_assignment": "Password or secret assignment",
}

_SARIF_SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"
_TOOL_URI = "https://github.com/sandeep-paluru/paste-guard"
_BASELINE_VERSION = 1
_PUBLIC_FIELDS = ("path", "line", "col", "rule", "severity", "mask", "length")
_HEX = frozenset("0123456789abcdef")
# Custom rules scan one line at a time, and stop after this many characters.
# A nested quantifier can still be slow inside that window.
_CUSTOM_LINE_CAP = 10000
_RULE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
_RULE_FIELDS = frozenset({
    "name", "regex", "severity", "keywords", "secret_group", "min_entropy", "description",
})


def severity(rule: str) -> str:
    return "coach" if rule in COACH_RULES else "block"


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


class CustomRule:
    """One user detector. keywords are already casefolded. secret_group 0 is the whole match."""

    def __init__(self, name, pattern, severity, description, source, keywords, secret_group, min_entropy):
        self.name = name
        self.pattern = pattern
        self.severity = severity
        self.description = description
        self.source = source
        self.keywords = keywords
        self.secret_group = secret_group
        self.min_entropy = min_entropy


class RuleSet:
    """Custom detectors loaded for one scan. Built-ins stay in RULES."""

    def __init__(self, custom=None):
        self.custom = list(custom or [])

    def known_names(self) -> set[str]:
        names = set(RULES)
        names.update(rule.name for rule in self.custom)
        return names


def _shannon(value: str) -> float:
    """Shannon entropy in bits per character. A single repeated character is 0."""
    if len(value) < 2:
        return 0.0
    counts: dict[str, int] = {}
    for ch in value:
        counts[ch] = counts.get(ch, 0) + 1
    length = len(value)
    entropy = 0.0
    for count in counts.values():
        p = count / length
        entropy -= p * math.log2(p)
    return entropy


def _match_custom(text: str, rule: CustomRule):
    """Matches of one custom rule. Each yield is (start, end, secret) in the whole text.

    The regex runs on one line, and only on the first _CUSTOM_LINE_CAP characters.
    A keyword list skips lines that contain none of them (case-insensitive).
    """
    offset = 0
    for line in text.splitlines(keepends=True):
        body = line
        if body.endswith("\r\n"):
            body = body[:-2]
        elif body.endswith(("\n", "\r")):
            body = body[:-1]
        if len(body) > _CUSTOM_LINE_CAP:
            body = body[:_CUSTOM_LINE_CAP]
        if rule.keywords:
            folded = body.casefold()
            if not any(word in folded for word in rule.keywords):
                offset += len(line)
                continue
        for match in rule.pattern.finditer(body):
            if match.end() == match.start():
                continue
            try:
                secret = match.group(rule.secret_group)
            except IndexError:
                continue
            if not secret:
                continue
            if rule.min_entropy is not None and _shannon(secret) < rule.min_entropy:
                continue
            yield offset + match.start(), offset + match.end(), secret
        offset += len(line)


def scan(text: str, ruleset: RuleSet | None = None) -> list[dict]:
    """Return non-overlapping findings. A specific credential rule always beats the generic
    password_assignment rule on overlap (so api_key="sk-ant-..." reports anthropic_key and blocks);
    otherwise the longest span wins, ties going to the rule defined first.
    Placeholder assignment values are dropped before that.
    The allowlist is not applied here. Detection stays the same; apply_allowlist drops
    known-safe hits from the verdict.

    ruleset adds custom detectors. They are specific rules, so they beat
    password_assignment on overlap. A tie on length goes to the earlier rule,
    and built-ins are earlier. A custom finding carries the captured secret
    and its severity. Built-in findings do not.
    """
    cands = []
    extra: dict[tuple[int, int, str], tuple[str, str]] = {}
    for order, (name, rx) in enumerate(RULES.items()):
        for m in rx.finditer(text):
            if not _keep_match(name, m):
                continue
            cands.append((name in GENERIC, m.start() - m.end(), order, m.start(), m.end(), name))
    if ruleset is not None and ruleset.custom:
        base = len(RULES)
        for index, rule in enumerate(ruleset.custom):
            for start, end, secret in _match_custom(text, rule):
                cands.append((False, start - end, base + index, start, end, rule.name))
                extra[(start, end, rule.name)] = (secret, rule.severity)
    cands.sort()
    findings = []
    for _, _, _, start, end, name in cands:
        if all(end <= f["start"] or start >= f["end"] for f in findings):
            item = {"type": name, "start": start, "end": end}
            found = extra.get((start, end, name))
            if found is not None:
                item["secret"] = found[0]
                item["severity"] = found[1]
            findings.append(item)
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


# Public documentation samples. Exact strings only, so a real key with a similar
# shape still matches. Sources:
# AWS access key id and secret: IAM programmatic access docs.
# Stripe test key: Stripe docs code samples (sk_test_ sample, not a live key).
# JWT: the jwt.io debugger sample (alg HS256, sub 1234567890, name John Doe).
def public_examples() -> list[str]:
    return [
        "AKIA" + "IOSFODNN7EXAMPLE",
        "wJalr" + "XUtnFEMI/" + "K7MDENG/" + "bPxRfiCY" + "EXAMPLEKEY",
        "sk" + "_test_" + "4eC39HqLyjWDarjtT1zdp7dc",
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
        + "eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ."
        + "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c",
    ]


_KINDS = ("value", "regex", "sha256")


class Allowlist:
    """Exact values, whole-value regexes, and sha256 hex digests."""

    def __init__(self, values: set[str], regexes: list, hashes: set[str], bad: list[str]):
        self.values = values
        self.regexes = regexes
        self.hashes = hashes
        self.bad = bad

    def __bool__(self) -> bool:
        return bool(self.values or self.regexes or self.hashes)

    def matches(self, candidate: str) -> bool:
        if candidate in self.values:
            return True
        if self.hashes and hashlib.sha256(candidate.encode("utf-8")).hexdigest() in self.hashes:
            return True
        return any(rx.fullmatch(candidate) for rx in self.regexes)


def parse_allowlist_line(line: str):
    """One file or config line. None if it is blank or a comment, an error string if it
    is unusable, or (kind, body) for a value, regex, or sha256 entry."""
    raw = line.strip()
    if not raw or raw.startswith("#"):
        return None
    kind, sep, body = raw.partition(":")
    if sep != ":" or kind not in _KINDS:
        return "unrecognised prefix (use value:, regex:, or sha256:)"
    if body == "":
        return "empty entry"
    if kind == "sha256" and not re.fullmatch(r"[0-9a-fA-F]{64}", body):
        return "sha256 must be 64 hex characters"
    if kind == "regex":
        try:
            re.compile(body)
        except re.error as ex:
            return f"bad regex ({ex})"
    return (kind, body.lower() if kind == "sha256" else body)


def _read_allowlist_file(path) -> tuple[list[tuple[str, str]], list[str]]:
    entries, bad = [], []
    text = path.read_text(encoding="utf-8")
    for n, line in enumerate(text.splitlines(), 1):
        parsed = parse_allowlist_line(line)
        if parsed is None:
            continue
        if isinstance(parsed, str):
            bad.append(f"{path.name}:{n}: {parsed}")
        else:
            entries.append(parsed)
    return entries, bad


def compile_allowlist(cfg: dict) -> Allowlist:
    """Build an allowlist from a [secrets] config table.

    cfg keys: examples (bool, default true), allowlist (list of prefixed strings),
    file (path, already resolved). A missing file is a startup error. A bad line is
    skipped and recorded on Allowlist.bad.
    """
    entries: list[tuple[str, str]] = []
    bad: list[str] = []
    if cfg.get("examples", True):
        entries.extend(("value", v) for v in public_examples())
    for i, item in enumerate(cfg.get("allowlist") or [], 1):
        if not isinstance(item, str):
            bad.append(f"allowlist[{i}]: not a string")
            continue
        parsed = parse_allowlist_line(item)
        if parsed is None:
            bad.append(f"allowlist[{i}]: empty")
            continue
        if isinstance(parsed, str):
            bad.append(f"allowlist[{i}]: {parsed}")
        else:
            entries.append(parsed)
    path = cfg.get("file") or ""
    if path:
        file = Path(path)
        if not file.is_file():
            raise SystemExit(f"secrets allowlist file not found: {file}")
        file_entries, file_bad = _read_allowlist_file(file)
        entries.extend(file_entries)
        bad.extend(file_bad)
    values, regexes, hashes = set(), [], set()
    for kind, body in entries:
        if kind == "value":
            values.add(body)
        elif kind == "regex":
            regexes.append(re.compile(body))
        else:
            hashes.add(body)
    allow = Allowlist(values, regexes, hashes, bad)
    for item in bad:
        print(f"paste-guard allowlist: skipped {item}", file=sys.stderr)
    return allow


def _candidates(text: str, finding: dict) -> list[str]:
    """Strings an allowlist entry can refer to. The whole match, and for assignments
    and database URLs the password with quotes removed.

    A custom rule also tries the captured secret, quotes stripped.
    """
    span = text[finding["start"]:finding["end"]]
    out = [span]
    secret = finding.get("secret")
    if secret:
        if secret not in out:
            out.append(secret)
        stripped, _quoted = _strip_value(secret)
        if stripped and stripped not in out:
            out.append(stripped)
        return out
    rule = RULES.get(finding["type"])
    if rule is not None and "value" in rule.groupindex:
        m = rule.search(span)
        if m:
            raw = m.group("value") or ""
            stripped, _ = _strip_value(raw)
            if raw and raw not in out:
                out.append(raw)
            if stripped and stripped not in out:
                out.append(stripped)
    return out


def apply_allowlist(text: str, findings: list[dict], allowlist: Allowlist) -> tuple[list[dict], int]:
    """Drop findings whose value is allowlisted. Returns the kept findings and how many were dropped.

    The dropped findings are not returned, so the value is not echoed. The count is
    the only record of them."""
    if not allowlist:
        return findings, 0
    kept = []
    dropped = 0
    for finding in findings:
        if any(allowlist.matches(value) for value in _candidates(text, finding)):
            dropped += 1
        else:
            kept.append(finding)
    return kept, dropped


# Dependency, VCS, and tool-cache folders. A directory walk does not descend into these.
SKIP_DIRS = frozenset({
    ".git", ".hg", ".svn",
    ".venv", "venv", ".tox", ".eggs",
    "node_modules", "bower_components",
    "vendor", "third_party", "third-party",
    "site-packages", "__pycache__",
    ".pytest_cache", ".mypy_cache", ".ruff_cache",
})
_SAMPLE = 8192


def _position(text: str, offset: int) -> tuple[int, int]:
    """1-based line and character column. Column counts characters, not bytes."""
    line = text.count("\n", 0, offset) + 1
    start = text.rfind("\n", 0, offset) + 1
    return line, offset - start + 1


def _secret_value(text: str, finding: dict) -> str:
    """The credential itself. For an assignment or a database URL, the password.

    A custom finding already carries the captured secret.
    """
    secret = finding.get("secret")
    if secret:
        return secret
    span = text[finding["start"]:finding["end"]]
    rule = RULES.get(finding["type"])
    if rule is not None and "value" in rule.groupindex:
        matched = rule.search(span)
        if matched:
            stripped, _quoted = _strip_value(matched.group("value") or "")
            if stripped:
                return stripped
    return span


def _mask(value: str) -> str:
    """First 4 characters and the length. The rest of the value is not included.

    A value of 4 characters or fewer would be the whole secret, so only the length is shown.
    """
    if len(value) <= 4:
        return f"({len(value)})"
    head = value[:4].replace("\r", "").replace("\n", "")
    return f"{head}({len(value)})"


def baseline_fingerprint(rule: str, value: str) -> str:
    """sha256 hex of the detector type, a NUL byte, and the raw value.

    A baseline file stores this next to the path. The value itself is not stored.
    """
    return hashlib.sha256(rule.encode("utf-8") + b"\0" + value.encode("utf-8")).hexdigest()


def _record(display: str, text: str, finding: dict) -> dict:
    value = _secret_value(text, finding)
    line, col = _position(text, finding["start"])
    rule = finding["type"]
    return {
        "path": display,
        "line": line,
        "col": col,
        "rule": rule,
        "severity": finding.get("severity") or severity(rule),
        "mask": _mask(value),
        "length": len(value),
        "fingerprint": baseline_fingerprint(rule, value),
    }


def _public_record(rec: dict) -> dict:
    """The finding as text and JSON show it. The fingerprint stays internal."""
    return {key: rec[key] for key in _PUBLIC_FIELDS}


def _summary(files: int, findings: int, block: int, coach: int, allowlisted: int,
             suppressed: int | None = None, inline: int | None = None) -> str:
    file_word = "file" if files == 1 else "files"
    finding_word = "finding" if findings == 1 else "findings"
    text = (
        f"scanned {files} {file_word}, {findings} {finding_word}, "
        f"{block} block, {coach} coach, {allowlisted} allowlisted"
    )
    # Inline stays between allowlisted and the baseline count. Both can be zero.
    if inline is not None:
        text += f", {inline} inline"
    if suppressed is not None:
        text += f", {suppressed} suppressed"
    return text


def _display(path: Path) -> str:
    try:
        rel = path.resolve().relative_to(Path.cwd().resolve())
    except ValueError:
        rel = path
    return rel.as_posix()


def _excluded(rel: str, patterns: list[str]) -> bool:
    if not patterns:
        return False
    rel = rel.replace("\\", "/")
    name = rel.rsplit("/", 1)[-1]
    parts = rel.split("/")
    suffixes = ["/".join(parts[i:]) for i in range(len(parts))]
    for pattern in patterns:
        pattern = pattern.replace("\\", "/")
        if not pattern:
            continue
        if fnmatch.fnmatch(rel, pattern) or ("/" not in pattern and fnmatch.fnmatch(name, pattern)):
            return True
        if any(fnmatch.fnmatch(suffix, pattern) for suffix in suffixes):
            return True
        try:
            if PurePosixPath(rel).match(pattern):
                return True
        except ValueError:
            continue
    return False


def _bytes_look_binary(chunk: bytes) -> bool:
    if b"\0" in chunk:
        return True
    if not chunk:
        return False
    try:
        chunk.decode("utf-8")
        return False
    except UnicodeDecodeError:
        pass
    # A sample can end in the middle of a code point. Only the trailing bytes are suspect.
    try:
        chunk[:-3].decode("utf-8")
    except UnicodeDecodeError:
        return True
    return False


def _read_text(path: Path) -> str | None:
    """File text, or None when the file is binary. OSError propagates."""
    with path.open("rb") as fh:
        sample = fh.read(_SAMPLE)
    if _bytes_look_binary(sample):
        return None
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None


def _read_stdin() -> str | None:
    data = sys.stdin.buffer.read()
    if _bytes_look_binary(data[:_SAMPLE]):
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _walk(root: Path, patterns: list[str]) -> tuple[list[Path], list[str]]:
    found = []
    problems = []

    def onerror(err):
        problems.append(f"cannot read {err.filename}: {err.strerror or err}")

    for dirpath, dirnames, filenames in os.walk(root, followlinks=False, onerror=onerror):
        kept = []
        for name in sorted(dirnames):
            if name in SKIP_DIRS:
                continue
            child = Path(dirpath) / name
            if _excluded(_display(child), patterns):
                continue
            kept.append(name)
        dirnames[:] = kept
        for name in sorted(filenames):
            path = Path(dirpath) / name
            if _excluded(_display(path), patterns):
                continue
            found.append(path)
    return found, problems


def _load_allowlist():
    """The [secrets] table, with PG_SECRETS_ALLOWLIST and PG_SECRETS_EXAMPLES applied."""
    import config
    cfg = config.load()
    return compile_allowlist(cfg["secrets"])


def _tool_version() -> str:
    path = Path(__file__).resolve().parents[1] / "VERSION"
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return "0.0.0"
    return text or "0.0.0"


def _sarif_level(severity_name: str) -> str:
    return "warning" if severity_name == "coach" else "error"


def _sarif_uri(path: str) -> str:
    """File URI relative to the working directory. Slashes stay literal."""
    return quote(path.replace("\\", "/"), safe="/")


def _sarif(records: list[dict], ruleset: RuleSet | None = None) -> dict:
    """SARIF 2.1.0. One rule per detector. The result message is only the mask.

    A record with inline set is kept and given a suppression of kind inSource,
    instead of being dropped. Text and JSON leave those findings out.
    Custom detectors are listed after the built-ins, with their description.
    """
    rules = []
    for name in RULES:
        rules.append({
            "id": name,
            "shortDescription": {"text": RULE_DESCRIPTIONS.get(name) or name},
            "defaultConfiguration": {"level": _sarif_level(severity(name))},
        })
    if ruleset is not None:
        for rule in ruleset.custom:
            rules.append({
                "id": rule.name,
                "shortDescription": {"text": rule.description or rule.name},
                "defaultConfiguration": {"level": _sarif_level(rule.severity)},
            })
    index = {rule["id"]: i for i, rule in enumerate(rules)}
    results = []
    for rec in records:
        rule_id = rec["rule"]
        if rule_id not in index:
            index[rule_id] = len(rules)
            rules.append({
                "id": rule_id,
                "shortDescription": {"text": RULE_DESCRIPTIONS.get(rule_id) or rule_id},
                "defaultConfiguration": {"level": _sarif_level(rec["severity"])},
            })
        result = {
            "ruleId": rule_id,
            "ruleIndex": index[rule_id],
            "level": _sarif_level(rec["severity"]),
            "message": {"text": rec["mask"]},
            "locations": [{
                "physicalLocation": {
                    "artifactLocation": {"uri": _sarif_uri(rec["path"])},
                    "region": {
                        "startLine": rec["line"],
                        "startColumn": rec["col"],
                    },
                },
            }],
        }
        # kind inSource is the SARIF name for a suppression written in the file.
        # status accepted is what GitHub code scanning uses to hide the alert.
        if rec.get("inline"):
            result["suppressions"] = [{"kind": "inSource", "status": "accepted"}]
        results.append(result)
    return {
        "$schema": _SARIF_SCHEMA,
        "version": "2.1.0",
        "runs": [{
            "tool": {
                "driver": {
                    "name": "paste-guard",
                    "version": _tool_version(),
                    "informationUri": _TOOL_URI,
                    "rules": rules,
                },
            },
            "columnKind": "unicodeCodePoints",
            "results": results,
        }],
    }


def _load_baseline(path: Path) -> tuple[set[tuple[str, str, str]] | None, str | None]:
    """Return (path, rule, fingerprint) keys, or an error string."""
    if not path.is_file():
        return None, f"pasteguard scan: baseline not found: {path}"
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as ex:
        return None, f"pasteguard scan: cannot read baseline: {path}: {ex.strerror or ex}"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None, f"pasteguard scan: baseline is not valid JSON: {path}"
    findings = data.get("findings") if isinstance(data, dict) else None
    if not isinstance(data, dict) or data.get("version") != _BASELINE_VERSION or not isinstance(findings, list):
        return None, f"pasteguard scan: unrecognized baseline file: {path}"
    keys = set()
    for item in findings:
        if not isinstance(item, dict):
            return None, f"pasteguard scan: unrecognized baseline file: {path}"
        rel, rule, fp = item.get("path"), item.get("rule"), item.get("fingerprint")
        if not isinstance(rel, str) or not isinstance(rule, str) or not isinstance(fp, str):
            return None, f"pasteguard scan: unrecognized baseline file: {path}"
        digest = fp.lower()
        if not rel or not rule or len(digest) != 64 or any(c not in _HEX for c in digest):
            return None, f"pasteguard scan: unrecognized baseline file: {path}"
        keys.add((rel.replace("\\", "/"), rule, digest))
    return keys, None


def _write_baseline(path: Path, records: list[dict]) -> str | None:
    """Replace path with the current findings. Returns an error string, or None.

    Each entry is the path, the detector, and the fingerprint. The raw value is not written.
    """
    if path.exists() and path.is_dir():
        return f"pasteguard scan: baseline is a directory: {path}"
    if not path.parent.exists():
        return f"pasteguard scan: baseline directory not found: {path.parent}"
    seen = set()
    findings = []
    for rec in records:
        item = (rec["path"], rec["rule"], rec["fingerprint"])
        if item in seen:
            continue
        seen.add(item)
        findings.append({
            "path": rec["path"],
            "rule": rec["rule"],
            "fingerprint": rec["fingerprint"],
        })
    text = json.dumps(
        {"version": _BASELINE_VERSION, "findings": findings},
        indent=2,
        ensure_ascii=False,
    ) + "\n"
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    except OSError as ex:
        try:
            tmp.unlink()
        except OSError:
            pass
        return f"pasteguard scan: cannot write baseline: {path}: {ex.strerror or ex}"
    return None


def _apply_baseline(records: list[dict], known: set[tuple[str, str, str]]) -> tuple[list[dict], int]:
    kept = []
    suppressed = 0
    for rec in records:
        if (rec["path"], rec["rule"], rec["fingerprint"]) in known:
            suppressed += 1
        else:
            kept.append(rec)
    return kept, suppressed


class _Marker:
    """One pasteguard:ignore or pasteguard:ignore-next-line on a source line.

    rules is None when every detector is covered. An empty set covers nothing,
    which is what an `=` with no names means. problems holds None for a missing
    name and the raw token for a name that is not a detector.
    """

    def __init__(self, line: int, kind: str, rules: set[str] | None, problems: list):
        self.line = line
        self.kind = kind
        self.rules = rules
        self.problems = problems
        self.used = False


def _split_lines(text: str) -> list[str]:
    """Lines in the same order _position and _line_count use. The newline is not kept."""
    if not text:
        return []
    parts = text.split("\n")
    if text.endswith("\n"):
        parts.pop()
    return parts


def _parse_rule_suffix(rest: str, known: set[str] | None = None) -> tuple[set[str] | None, list, int]:
    """Optional `=rule,rule` after the marker keyword.

    None means the marker names no rules, so it covers every detector.
    The returned index is how far into rest the suffix reached.
    known is the detector names that count. The default is the built-in set.
    """
    i = 0
    n = len(rest)
    while i < n and rest[i] in " \t":
        i += 1
    if i >= n or rest[i] != "=":
        return None, [], 0
    i += 1
    names: list[str] = []
    while i < n:
        while i < n and rest[i] in " \t":
            i += 1
        if i < n and rest[i] == ",":
            i += 1
            continue
        j = i
        while j < n and (rest[j].isalnum() or rest[j] in "_-"):
            j += 1
        if j == i:
            break
        # An HTML closer is `-->`. The hyphens are not part of the rule id.
        raw = rest[i:j].rstrip("-")
        if not raw:
            break
        names.append(raw)
        i = j
        while i < n and rest[i] in " \t":
            i += 1
        if i < n and rest[i] == ",":
            i += 1
            continue
        break
    if not names:
        return set(), [None], i
    problems = []
    seen = set()
    catalog = set(RULES) if known is None else known
    matched = set()
    for name in names:
        if name in catalog:
            matched.add(name)
        elif name not in seen:
            problems.append(name)
            seen.add(name)
    return matched, problems, i


def _parse_marker_at(line: str, start: int, known: set[str] | None = None):
    """One marker starting at start, or None when the text only shares a prefix.

    `pasteguard:ignored` is not a marker. `pasteguard:ignore-next-line` is the
    next-line form and is not also a same-line ignore.
    """
    key = "pasteguard:ignore"
    if not line.startswith(key, start):
        return None
    pos = start + len(key)
    kind = "line"
    if line.startswith("-next-line", pos):
        after = pos + len("-next-line")
        if after < len(line) and (line[after].isalnum() or line[after] == "_"):
            return None
        kind = "next"
        pos = after
    elif pos < len(line) and (line[pos].isalnum() or line[pos] == "_"):
        return None
    rules, problems, consumed = _parse_rule_suffix(line[pos:], known)
    return kind, rules, problems, pos + consumed


def _parse_markers(text: str, known: set[str] | None = None) -> list[_Marker]:
    """Every marker in the file. The comment syntax around it is irrelevant.

    known is the detector names a `=rule` list may name. The default is the
    built-in set, which is what the server and a scan with no custom rules use.
    """
    found = []
    for number, line in enumerate(_split_lines(text), 1):
        start = 0
        while True:
            at = line.find("pasteguard:ignore", start)
            if at < 0:
                break
            parsed = _parse_marker_at(line, at, known)
            if parsed is None:
                start = at + 1
                continue
            kind, rules, problems, end = parsed
            found.append(_Marker(number, kind, rules, problems))
            start = end
    return found


def _marker_covers(marker: _Marker, rule: str) -> bool:
    return marker.rules is None or rule in marker.rules


def _marker_in_scope(marker: _Marker, scope: set[int] | None, line_count: int) -> bool:
    """scope None means the whole file. Otherwise the target line has to be in it.

    ignore-next-line targets the following line. A marker on the last added
    line whose next line does not exist is still in scope, so it can be reported
    as unused.
    """
    if scope is None:
        return True
    target = marker.line if marker.kind == "line" else marker.line + 1
    if target in scope:
        return True
    return marker.line in scope and target > line_count


def _apply_inline(text: str, findings: list[dict], markers: list[_Marker],
                  scope: set[int] | None) -> tuple[list[dict], list[dict], list[_Marker]]:
    """Drop findings a marker covers. A multi-line span uses its first line only.

    Returns kept findings, suppressed findings, and in-scope markers that
    suppressed nothing.
    """
    same: dict[int, list[_Marker]] = {}
    nxt: dict[int, list[_Marker]] = {}
    for marker in markers:
        if marker.kind == "line":
            same.setdefault(marker.line, []).append(marker)
        else:
            nxt.setdefault(marker.line + 1, []).append(marker)
    kept = []
    suppressed = []
    for finding in findings:
        line = text.count("\n", 0, finding["start"]) + 1
        rule = finding["type"]
        hit = [marker for marker in same.get(line, ()) if _marker_covers(marker, rule)]
        hit.extend(marker for marker in nxt.get(line, ()) if _marker_covers(marker, rule))
        if hit:
            for marker in hit:
                marker.used = True
            suppressed.append(finding)
        else:
            kept.append(finding)
    line_count = _line_count(text)
    unused = [
        marker for marker in markers
        if not marker.used and _marker_in_scope(marker, scope, line_count)
    ]
    return kept, suppressed, unused


def _marker_warnings(path: str, markers: list[_Marker]) -> list[str]:
    lines = []
    for marker in markers:
        for item in marker.problems:
            if item is None:
                lines.append(
                    f"pasteguard scan: {path}:{marker.line}: pasteguard:ignore is missing a rule name"
                )
            else:
                lines.append(
                    f"pasteguard scan: {path}:{marker.line}: unknown rule '{item}' in pasteguard:ignore"
                )
    return lines


def _unused_pairs(path: str, markers: list[_Marker]) -> list[tuple[str, int]]:
    seen = set()
    pairs = []
    for marker in markers:
        key = (path, marker.line)
        if key in seen:
            continue
        seen.add(key)
        pairs.append(key)
    return pairs


def _analyze(display: str, text: str, allow, scope: set[int] | None, inline_on: bool,
             ruleset: RuleSet | None = None):
    """Scan one blob. scope limits which lines can produce a finding (None means all).

    The allowlist runs first. An allowlisted value is not counted as inline, and a
    marker that only sat on one is unused. Returns records, inline records,
    allowlisted count, warnings, and unused marker locations.
    """
    findings = scan(text, ruleset)
    if scope is not None:
        findings = [item for item in findings if _on_added_lines(text, item, scope)]
    kept, dropped = apply_allowlist(text, findings, allow)
    inline_findings: list[dict] = []
    warnings: list[str] = []
    unused: list[tuple[str, int]] = []
    if inline_on:
        known = ruleset.known_names() if ruleset is not None else None
        markers = _parse_markers(text, known)
        kept, inline_findings, stale = _apply_inline(text, kept, markers, scope)
        # Only markers that could affect this scan. A typo on a line the diff
        # did not touch stays quiet.
        visible = [marker for marker in markers if _marker_in_scope(marker, scope, _line_count(text))]
        warnings = _marker_warnings(display, visible)
        unused = _unused_pairs(display, stale)
    records = [_record(display, text, finding) for finding in kept]
    inline_records = [_record(display, text, finding) for finding in inline_findings]
    for rec in inline_records:
        rec["inline"] = True
    return records, inline_records, dropped, warnings, unused


def _emit(records: list[dict], inline_records: list[dict], unused_lines: list[str],
          summary: str, fmt: str, ruleset: RuleSet | None = None) -> None:
    """Text and JSON list the findings that remain. SARIF also lists inline ones.

    Unused-marker lines share a stream with the summary, so a JSON or SARIF
    parser never sees them on stdout.
    """
    if fmt == "json":
        json.dump([_public_record(rec) for rec in records], sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
        for line in unused_lines:
            print(line, file=sys.stderr)
        print(summary, file=sys.stderr)
        return
    if fmt == "sarif":
        combined = sorted(
            records + inline_records,
            key=lambda rec: (rec["path"], rec["line"], rec["col"], rec["rule"]),
        )
        json.dump(_sarif(combined, ruleset), sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
        for line in unused_lines:
            print(line, file=sys.stderr)
        print(summary, file=sys.stderr)
        return
    for rec in records:
        print(f"{rec['path']}:{rec['line']}:{rec['col']} {rec['rule']} {rec['severity']} {rec['mask']}")
    for line in unused_lines:
        print(line)
    print(summary)


_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def _git(args: list[str]) -> subprocess.CompletedProcess:
    """Run git in the current directory. Diff settings that would change hunks are pinned."""
    cmd = [
        "git",
        "-c", "diff.renames=true",
        "-c", "diff.suppressBlankEmpty=false",
        "-c", "core.quotePath=false",
        *args,
    ]
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    return subprocess.run(cmd, capture_output=True, check=False, env=env)


def _git_err(proc: subprocess.CompletedProcess, fallback: str) -> str:
    lines = proc.stderr.decode("utf-8", "replace").strip().splitlines()
    return lines[-1] if lines else fallback


def _require_work_tree() -> str | None:
    try:
        proc = _git(["rev-parse", "--is-inside-work-tree"])
    except FileNotFoundError:
        return "pasteguard scan: git is not available"
    if proc.returncode != 0 or proc.stdout.strip() != b"true":
        return "pasteguard scan: not a git repository"
    return None


def _repo_root() -> Path:
    proc = _git(["rev-parse", "--show-toplevel"])
    return Path(proc.stdout.decode("utf-8", "surrogateescape").splitlines()[0])


def _resolve_diff_base(ref: str) -> tuple[str, str] | str:
    """SHAs for `git diff REF...HEAD`: merge-base, then HEAD. Or an error string."""
    if _git(["rev-parse", "--verify", "--quiet", "--end-of-options", "HEAD"]).returncode != 0:
        return "pasteguard scan: no commits yet to compare against"
    peeled = ref + "^{commit}"
    if _git(["rev-parse", "--verify", "--quiet", "--end-of-options", peeled]).returncode != 0:
        return f"pasteguard scan: ref not found: {ref}"
    base = _git(["merge-base", "--end-of-options", ref, "HEAD"])
    head = _git(["rev-parse", "--verify", "--end-of-options", "HEAD"])
    if base.returncode != 0 or head.returncode != 0 or not base.stdout.strip():
        return f"pasteguard scan: no merge base between {ref} and HEAD"
    return base.stdout.decode().strip(), head.stdout.decode().strip()


def _parse_name_status(blob: bytes) -> list[tuple[str, str, str | None]]:
    """(status letter, new path, old path). Renames carry the source path."""
    parts = blob.split(b"\0")
    if parts and parts[-1] == b"":
        parts.pop()
    entries = []
    i = 0
    while i < len(parts):
        status = parts[i].decode("utf-8", "surrogateescape")
        i += 1
        kind = status[:1]
        if kind in ("R", "C"):
            if i + 1 >= len(parts):
                break
            old = parts[i].decode("utf-8", "surrogateescape")
            new = parts[i + 1].decode("utf-8", "surrogateescape")
            i += 2
            entries.append((kind, new, old))
            continue
        if i >= len(parts):
            break
        path = parts[i].decode("utf-8", "surrogateescape")
        i += 1
        entries.append((kind, path, None))
    return entries


def _parse_added_lines(diff: bytes) -> set[int] | None:
    """1-based line numbers added in the new file. None when git calls the diff binary.

    Once a hunk starts, every '+' line is an added line, including a line whose
    text itself starts with '+'. '+++' is only a header, and it sits before the
    first hunk.
    """
    text = diff.decode("utf-8", "replace")
    added: set[int] = set()
    new_line = None
    for line in text.splitlines():
        if line.startswith("Binary files ") and line.endswith(" differ"):
            return None
        if line.startswith("GIT binary patch"):
            return None
        match = _HUNK_RE.match(line)
        if match:
            new_line = int(match.group(1))
            continue
        if new_line is None:
            continue
        if line.startswith("+"):
            added.add(new_line)
            new_line += 1
        elif line.startswith("-") or line.startswith("\\"):
            continue
        else:
            new_line += 1
    return added


def _line_count(text: str) -> int:
    if not text:
        return 0
    count = text.count("\n")
    if not text.endswith("\n"):
        count += 1
    return count


def _on_added_lines(text: str, finding: dict, added: set[int]) -> bool:
    """True when every line the finding touches was added.

    A secret that sits on an unchanged line, or that runs onto one, is not
    part of this diff. Offsets are into the new file.
    """
    start, end = finding["start"], finding["end"]
    if end <= start:
        return False
    first = text.count("\n", 0, start) + 1
    last = text.count("\n", 0, end - 1) + 1
    return all(line in added for line in range(first, last + 1))


def _skipped_vendor(rel: str) -> bool:
    """A parent directory the walker would not descend into."""
    parts = rel.split("/")
    return any(part in SKIP_DIRS for part in parts[:-1])


def _text_from_bytes(data: bytes) -> str | None:
    if _bytes_look_binary(data[:_SAMPLE]):
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _read_blob(spec: str) -> tuple[bytes | None, str | None, str | None]:
    """(bytes, git object type, error). Non-blobs (a submodule commit) have no bytes and no error."""
    kind = _git(["cat-file", "-t", spec])
    if kind.returncode != 0:
        return None, None, _git_err(kind, "cannot read")
    obj_type = kind.stdout.decode().strip()
    if obj_type != "blob":
        return None, obj_type, None
    data = _git(["cat-file", "-p", spec])
    if data.returncode != 0:
        return None, obj_type, _git_err(data, "cannot read")
    return data.stdout, obj_type, None


def _blob_diff(old: str, new: str) -> tuple[bytes, str | None]:
    proc = _git([
        "diff", "-U0", "--no-color", "--no-ext-diff", "--no-textconv", old, new,
    ])
    if proc.returncode != 0:
        return b"", _git_err(proc, "git diff failed")
    return proc.stdout, None


def _changed_entries(staged: bool, diff_range: tuple[str, str] | None) -> tuple[list[tuple[str, str, str | None]], str | None]:
    if staged:
        cmd = ["diff", "--cached", "--find-renames", "--name-status", "-z"]
    else:
        assert diff_range is not None
        cmd = ["diff", "--find-renames", "--name-status", "-z", diff_range[0], diff_range[1]]
    proc = _git(cmd)
    if proc.returncode != 0:
        return [], "pasteguard scan: " + _git_err(proc, "git diff failed")
    return _parse_name_status(proc.stdout), None


def _scan_diff(staged: bool, diff_range: tuple[str, str] | None, patterns: list[str], allow, inline_on: bool,
               ruleset: RuleSet | None = None):
    """Scan added lines. Returns a result tuple, or an error string.

    The tuple is (records, inline records, files, allowlisted, warnings, unused, errors).
    `--staged` reads the index (`:path`), so the working tree is irrelevant.
    `--diff-base` reads `HEAD:path` and compares commits: the merge-base of REF
    and HEAD against HEAD. Uncommitted edits are not part of that diff.
    A marker in that blob counts even when the marker line itself was not added.
    """
    entries, fatal = _changed_entries(staged, diff_range)
    if fatal:
        return fatal
    try:
        root = _repo_root()
    except (IndexError, OSError):
        return "pasteguard scan: not a git repository"

    head = None if staged else diff_range[1]
    base = None if staged else diff_range[0]
    records: list[dict] = []
    inline_records: list[dict] = []
    files = 0
    allowlisted = 0
    warnings: list[str] = []
    unused: list[tuple[str, int]] = []
    errors: list[str] = []
    seen = set()
    for kind, path, old in entries:
        if kind == "D":
            continue
        if kind == "U":
            return f"pasteguard scan: unmerged file: {path}"
        if path in seen or _skipped_vendor(path):
            continue
        seen.add(path)
        display = _display(root / path)
        if _excluded(display, patterns):
            continue
        new_spec = f":{path}" if staged else f"{head}:{path}"
        data, obj_type, read_error = _read_blob(new_spec)
        if read_error:
            errors.append(f"cannot read {display}: {read_error}")
            continue
        if obj_type != "blob" or data is None:
            continue
        text = _text_from_bytes(data)
        if text is None:
            continue
        if kind in ("A", "C"):
            added = set(range(1, _line_count(text) + 1))
        else:
            old_spec = f"HEAD:{old or path}" if staged else f"{base}:{old or path}"
            diff, diff_error = _blob_diff(old_spec, new_spec)
            if diff_error:
                errors.append(f"cannot diff {display}: {diff_error}")
                continue
            added = _parse_added_lines(diff)
            if added is None:
                continue
        if not added:
            continue
        rows, hidden, dropped, warns, stale = _analyze(display, text, allow, added, inline_on, ruleset)
        files += 1
        allowlisted += dropped
        records.extend(rows)
        inline_records.extend(hidden)
        warnings.extend(warns)
        unused.extend(stale)
    return records, inline_records, files, allowlisted, warnings, unused, errors


def _scan_planned(planned: list, patterns: list[str], allow, inline_on: bool,
                  ruleset: RuleSet | None = None):
    stdin_text = None
    stdin_done = False
    if any(item is None for item in planned):
        stdin_text = _read_stdin()

    records: list[dict] = []
    inline_records: list[dict] = []
    files = 0
    allowlisted = 0
    warnings: list[str] = []
    unused: list[tuple[str, int]] = []
    errors: list[str] = []
    seen = set()
    for item in planned:
        if item is None:
            if stdin_done:
                continue
            stdin_done = True
            if stdin_text is None:
                continue
            rows, hidden, dropped, warns, stale = _analyze("-", stdin_text, allow, None, inline_on, ruleset)
            files += 1
            allowlisted += dropped
            records.extend(rows)
            inline_records.extend(hidden)
            warnings.extend(warns)
            unused.extend(stale)
            continue
        try:
            key = str(item.resolve())
            display = _display(item)
        except OSError as ex:
            errors.append(f"cannot read {item.as_posix()}: {ex.strerror or ex}")
            continue
        if _excluded(display, patterns):
            continue
        if key in seen:
            continue
        seen.add(key)
        try:
            text = _read_text(item)
        except OSError as ex:
            errors.append(f"cannot read {display}: {ex.strerror or ex}")
            continue
        if text is None:
            continue
        rows, hidden, dropped, warns, stale = _analyze(display, text, allow, None, inline_on, ruleset)
        files += 1
        allowlisted += dropped
        records.extend(rows)
        inline_records.extend(hidden)
        warnings.extend(warns)
        unused.extend(stale)
    return records, inline_records, files, allowlisted, warnings, unused, errors


def _parse_one_rule(item, source: str, index: int, seen: set[str]) -> tuple[CustomRule | None, str | None]:
    """One [[scan.rules]] table. The error names the rule once its name is known."""
    where = f"pasteguard scan: {source}: scan.rules[{index}]"
    if not isinstance(item, dict):
        return None, f"{where}: expected a table"
    raw_name = item.get("name")
    if not isinstance(raw_name, str) or not raw_name:
        return None, f"{where}: missing name"
    where = f"pasteguard scan: {source}: rule {raw_name}"
    if not _RULE_NAME.fullmatch(raw_name):
        return None, f"{where}: name must use letters, digits, '_' or '-'"
    if raw_name in RULES:
        return None, f"{where}: name matches a built-in detector"
    if raw_name in seen:
        return None, f"{where}: duplicate name"
    unknown = [key for key in item if key not in _RULE_FIELDS]
    if unknown:
        return None, f"{where}: unknown field '{unknown[0]}'"

    pattern = item.get("regex")
    if not isinstance(pattern, str) or pattern == "":
        return None, f"{where}: missing regex"
    try:
        compiled = re.compile(pattern)
    except re.error as ex:
        return None, f"{where}: bad regex ({ex})"

    if "severity" not in item:
        return None, f"{where}: missing severity"
    sev = item.get("severity")
    if sev not in ("block", "coach"):
        if isinstance(sev, str):
            return None, f"{where}: unknown severity '{sev}'"
        return None, f"{where}: unknown severity"

    group = item.get("secret_group", 0)
    if isinstance(group, bool) or not isinstance(group, int):
        return None, f"{where}: secret_group must be an integer"
    if group < 0 or group > compiled.groups:
        return None, f"{where}: secret_group {group} is out of range"

    raw_keywords = item.get("keywords", [])
    if raw_keywords is None:
        raw_keywords = []
    if isinstance(raw_keywords, str) or not isinstance(raw_keywords, list):
        return None, f"{where}: keywords must be a list of strings"
    words: list[str] = []
    for word in raw_keywords:
        if not isinstance(word, str) or word.strip() == "":
            return None, f"{where}: keywords must be a list of strings"
        folded = word.casefold()
        if folded not in words:
            words.append(folded)

    min_entropy = None
    if "min_entropy" in item and item.get("min_entropy") is not None:
        ent = item.get("min_entropy")
        if isinstance(ent, bool) or not isinstance(ent, (int, float)):
            return None, f"{where}: min_entropy must be a number"
        if ent < 0 or ent != ent or ent == float("inf"):
            return None, f"{where}: min_entropy must be zero or greater"
        min_entropy = float(ent)

    desc = item.get("description", "")
    if desc is None:
        desc = ""
    if not isinstance(desc, str):
        return None, f"{where}: description must be a string"
    description = desc.strip() or raw_name
    return CustomRule(
        raw_name, compiled, sev, description, source, tuple(words), group, min_entropy,
    ), None


def _rules_from_document(doc, source: str, seen: set[str], require: bool) -> tuple[list[CustomRule], str | None]:
    """Pull [[scan.rules]] out of a parsed TOML document.

    require is for --rules, which has to contain the table. paste-guard.toml
    may omit it.
    """
    if not isinstance(doc, dict):
        return [], f"pasteguard scan: {source}: no [[scan.rules]] table"
    if "scan" not in doc:
        if require:
            return [], f"pasteguard scan: {source}: no [[scan.rules]] table"
        return [], None
    scan = doc.get("scan")
    if not isinstance(scan, dict):
        return [], f"pasteguard scan: {source}: scan must be a table"
    if "rules" not in scan:
        if require:
            return [], f"pasteguard scan: {source}: no [[scan.rules]] table"
        return [], None
    rules = scan.get("rules")
    if not isinstance(rules, list):
        return [], f"pasteguard scan: {source}: scan.rules must be an array of tables"
    parsed: list[CustomRule] = []
    for index, item in enumerate(rules):
        rule, err = _parse_one_rule(item, source, index, seen)
        if err:
            return [], err
        assert rule is not None
        seen.add(rule.name)
        parsed.append(rule)
    return parsed, None


def _load_custom_rules(rules_path: str | None) -> tuple[RuleSet | None, str | None]:
    """Rules from paste-guard.toml, then from --rules. An error string exits 2.

    The same name twice, or a name that is already a built-in, is an error.
    The rules file uses the same [[scan.rules]] tables as the config.
    """
    try:
        import config
        cfg = config.load()
    except SystemExit as ex:
        message = ex.code
        if isinstance(message, str) and message.strip():
            return None, message.strip()
        return None, "pasteguard scan: cannot read config"
    except Exception as ex:
        if type(ex).__name__ == "TOMLDecodeError":
            return None, f"pasteguard scan: {ex}"
        raise
    source = Path(config.CONFIG_PATH).name
    seen: set[str] = set()
    custom, err = _rules_from_document(cfg, source, seen, require=False)
    if err:
        return None, err
    if rules_path:
        path = Path(rules_path)
        if not path.is_file():
            return None, f"pasteguard scan: rules file not found: {rules_path}"
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as ex:
            return None, f"pasteguard scan: cannot read rules file: {rules_path}: {ex.strerror or ex}"
        try:
            doc = tomllib.loads(text)
        except Exception as ex:
            if type(ex).__name__ == "TOMLDecodeError":
                return None, f"pasteguard scan: rules file is not valid TOML: {rules_path}: {ex}"
            raise
        extra, err = _rules_from_document(doc, path.name, seen, require=True)
        if err:
            return None, err
        custom.extend(extra)
    return RuleSet(custom), None


def _print_rule_list(ruleset: RuleSet) -> None:
    """name, severity, and where the detector came from. Built-ins first."""
    for name in RULES:
        print(f"{name} {severity(name)} built-in")
    for rule in ruleset.custom:
        print(f"{rule.name} {rule.severity} {rule.source}")


def _load_scan_allowlist():
    """The [secrets] allowlist, or an error string to print (exit 2)."""
    try:
        return _load_allowlist(), None
    except SystemExit as ex:
        message = ex.code
        if isinstance(message, str) and message.strip():
            return None, message.strip()
        return None, ""
    except Exception as ex:
        if type(ex).__name__ == "TOMLDecodeError":
            return None, f"pasteguard scan: {ex}"
        raise


def _report_scan(records, inline_records, files, allowlisted, warnings, unused, errors, args, baseline_keys,
                 ruleset: RuleSet | None = None) -> int:
    for message in errors:
        print(f"pasteguard scan: {message}", file=sys.stderr)
    for message in warnings:
        print(message, file=sys.stderr)
    records.sort(key=lambda rec: (rec["path"], rec["line"], rec["col"], rec["rule"]))
    inline_records.sort(key=lambda rec: (rec["path"], rec["line"], rec["col"], rec["rule"]))
    unused = sorted(unused)

    write_error = None
    if args.write_baseline:
        # Record every current finding, including ones a baseline would suppress.
        # Inline-suppressed findings are already gone, same as allowlisted ones.
        write_error = _write_baseline(Path(args.write_baseline), records)
        if write_error:
            print(write_error, file=sys.stderr)

    suppressed = None
    if baseline_keys is not None:
        records, suppressed = _apply_baseline(records, baseline_keys)

    block = sum(1 for rec in records if rec["severity"] == "block")
    coach = sum(1 for rec in records if rec["severity"] == "coach")
    inline_count = None if args.no_inline_ignore else len(inline_records)
    unused_lines = []
    if args.report_unused_ignores and not args.no_inline_ignore:
        unused_lines = [f"{path}:{line} unused pasteguard:ignore" for path, line in unused]
    _emit(
        records,
        inline_records,
        unused_lines,
        _summary(files, len(records), block, coach, allowlisted, suppressed, inline_count),
        args.format,
        ruleset,
    )
    if write_error or errors:
        return 2
    failed = bool(block or coach) if args.fail_on == "coach" else bool(block)
    if unused_lines:
        failed = True
    return 1 if failed else 0


def cmd_scan(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="pasteguard scan",
        description="Scan files or stdin for secrets. Does not load the model or the index.",
    )
    parser.add_argument("paths", nargs="*", help="files or directories to scan; - or no path reads stdin")
    parser.add_argument("--exclude", action="append", default=[], metavar="GLOB",
                        help="skip paths matching GLOB, repeatable")
    parser.add_argument("--format", choices=("text", "json", "sarif"), default="text",
                        help="text lines, a JSON list, or SARIF 2.1.0 (default: text)")
    parser.add_argument("--fail-on", choices=("block", "coach"), default="block", dest="fail_on",
                        help="exit 1 at this severity; coach also fails coach-level detectors")
    parser.add_argument("--rules", metavar="FILE",
                        help="TOML file of extra [[scan.rules]] detectors, added to paste-guard.toml")
    parser.add_argument("--list-rules", action="store_true", dest="list_rules",
                        help="print built-in and custom detectors with severity and source, then exit")
    parser.add_argument("--baseline", metavar="PATH",
                        help="suppress findings whose path and fingerprint are in this file")
    parser.add_argument("--write-baseline", metavar="PATH", dest="write_baseline",
                        help="write current findings as path and sha256 fingerprints, without the secret")
    parser.add_argument("--staged", action="store_true",
                        help="scan only lines added in the index (git diff --cached); reads the staged blob, not the working tree")
    parser.add_argument("--diff-base", metavar="REF",
                        help="scan only lines added since the merge-base of REF and HEAD (git diff REF...HEAD); compares commits")
    parser.add_argument("--no-inline-ignore", action="store_true", dest="no_inline_ignore",
                        help="do not honor pasteguard:ignore comments")
    parser.add_argument("--report-unused-ignores", action="store_true", dest="report_unused_ignores",
                        help="print pasteguard:ignore markers that suppressed nothing, and exit 1 if any")
    try:
        args = parser.parse_args(argv)
    except SystemExit as ex:
        code = ex.code
        return code if isinstance(code, int) else 2

    if args.list_rules:
        if args.paths or args.staged or args.diff_base:
            print("pasteguard scan: --list-rules does not take path arguments", file=sys.stderr)
            return 2
        listed, list_error = _load_custom_rules(args.rules)
        if list_error:
            print(list_error, file=sys.stderr)
            return 2
        _print_rule_list(listed)
        return 0

    if args.staged and args.diff_base:
        print("pasteguard scan: use either --staged or --diff-base", file=sys.stderr)
        return 2
    if (args.staged or args.diff_base) and args.paths:
        flag = "--staged" if args.staged else "--diff-base"
        print(f"pasteguard scan: {flag} does not take path arguments", file=sys.stderr)
        return 2

    diff_range = None
    if args.staged or args.diff_base:
        repo_error = _require_work_tree()
        if repo_error:
            print(repo_error, file=sys.stderr)
            return 2
        if args.diff_base:
            resolved = _resolve_diff_base(args.diff_base)
            if isinstance(resolved, str):
                print(resolved, file=sys.stderr)
                return 2
            diff_range = resolved

    patterns = [item for item in args.exclude if item]
    planned: list = []
    walk_errors: list[str] = []
    if not args.staged and not args.diff_base:
        for raw in args.paths or ["-"]:
            if raw == "-":
                planned.append(None)
                continue
            path = Path(raw)
            if not path.exists():
                print(f"pasteguard scan: not found: {raw}", file=sys.stderr)
                return 2
            if path.is_file():
                planned.append(path)
            elif path.is_dir():
                found, problems = _walk(path, patterns)
                planned.extend(found)
                walk_errors.extend(problems)
            else:
                print(f"pasteguard scan: not a file or directory: {raw}", file=sys.stderr)
                return 2

    ruleset, rules_error = _load_custom_rules(args.rules)
    if rules_error:
        print(rules_error, file=sys.stderr)
        return 2

    allow, allow_error = _load_scan_allowlist()
    if allow_error is not None:
        if allow_error:
            print(allow_error, file=sys.stderr)
        return 2

    baseline_keys = None
    if args.baseline:
        baseline_keys, baseline_error = _load_baseline(Path(args.baseline))
        if baseline_error:
            print(baseline_error, file=sys.stderr)
            return 2

    inline_on = not args.no_inline_ignore
    if args.staged or args.diff_base:
        scanned = _scan_diff(args.staged, diff_range, patterns, allow, inline_on, ruleset)
        if isinstance(scanned, str):
            print(scanned, file=sys.stderr)
            return 2
        records, inline_records, files, allowlisted, warnings, unused, errors = scanned
    else:
        records, inline_records, files, allowlisted, warnings, unused, errors = _scan_planned(
            planned, patterns, allow, inline_on, ruleset,
        )
        errors = walk_errors + errors
    return _report_scan(
        records, inline_records, files, allowlisted, warnings, unused, errors, args, baseline_keys,
        ruleset,
    )


def fingerprint_bytes(data: bytes) -> str:
    """sha256 hex of a secret. One trailing newline is ignored so `echo secret | pasteguard fingerprint` works."""
    if data.endswith(b"\r\n"):
        data = data[:-2]
    elif data.endswith(b"\n"):
        data = data[:-1]
    return hashlib.sha256(data).hexdigest()


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv == ["fingerprint"]:
        print(fingerprint_bytes(sys.stdin.buffer.read()))
        return 0
    if argv[0] == "scan":
        return cmd_scan(argv[1:])
    print("usage: python secrets_scan.py [fingerprint | scan [options] [PATH ...]]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
