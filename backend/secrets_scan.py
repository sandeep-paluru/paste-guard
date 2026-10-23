"""Secrets and PII scanner.

Regex rules for common credentials, connection URLs, and password assignments.
Known-safe values are filtered afterwards by apply_allowlist, so a documented
sample key can be ignored without changing what scan() detects.

`pasteguard scan` runs these rules on files or stdin. It does not load the
model, the index, or the server.
"""
import argparse
import fnmatch
import hashlib
import json
import os
import re
import sys
from pathlib import Path, PurePosixPath

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


def scan(text: str) -> list[dict]:
    """Return non-overlapping findings. A specific credential rule always beats the generic
    password_assignment rule on overlap (so api_key="sk-ant-..." reports anthropic_key and blocks);
    otherwise the longest span wins, ties going to the rule defined first.
    Placeholder assignment values are dropped before that.
    The allowlist is not applied here. Detection stays the same; apply_allowlist drops
    known-safe hits from the verdict."""
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
    and database URLs the password with quotes removed."""
    span = text[finding["start"]:finding["end"]]
    out = [span]
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
    """The credential itself. For an assignment or a database URL, the password."""
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


def _record(display: str, text: str, finding: dict) -> dict:
    value = _secret_value(text, finding)
    line, col = _position(text, finding["start"])
    return {
        "path": display,
        "line": line,
        "col": col,
        "rule": finding["type"],
        "severity": severity(finding["type"]),
        "mask": _mask(value),
        "length": len(value),
    }


def _summary(files: int, findings: int, block: int, coach: int, allowlisted: int) -> str:
    file_word = "file" if files == 1 else "files"
    finding_word = "finding" if findings == 1 else "findings"
    return (
        f"scanned {files} {file_word}, {findings} {finding_word}, "
        f"{block} block, {coach} coach, {allowlisted} allowlisted"
    )


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


def _scan_one(display: str, text: str, allow) -> tuple[list[dict], int]:
    kept, dropped = apply_allowlist(text, scan(text), allow)
    return [_record(display, text, finding) for finding in kept], dropped


def _load_allowlist():
    """The [secrets] table, with PG_SECRETS_ALLOWLIST and PG_SECRETS_EXAMPLES applied."""
    import config
    cfg = config.load()
    return compile_allowlist(cfg["secrets"])


def _emit(records: list[dict], summary: str, fmt: str) -> None:
    if fmt == "json":
        json.dump(records, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
        print(summary, file=sys.stderr)
        return
    for rec in records:
        print(f"{rec['path']}:{rec['line']}:{rec['col']} {rec['rule']} {rec['severity']} {rec['mask']}")
    print(summary)


def cmd_scan(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="pasteguard scan",
        description="Scan files or stdin for secrets. Does not load the model or the index.",
    )
    parser.add_argument("paths", nargs="*", help="files or directories to scan; - or no path reads stdin")
    parser.add_argument("--exclude", action="append", default=[], metavar="GLOB",
                        help="skip paths matching GLOB, repeatable")
    parser.add_argument("--format", choices=("text", "json"), default="text",
                        help="text lines, or a JSON list (default: text)")
    parser.add_argument("--fail-on", choices=("block", "coach"), default="block", dest="fail_on",
                        help="exit 1 at this severity; coach also fails JWTs and password assignments")
    try:
        args = parser.parse_args(argv)
    except SystemExit as ex:
        code = ex.code
        return code if isinstance(code, int) else 2

    patterns = [item for item in args.exclude if item]
    paths = args.paths or ["-"]
    planned: list = []
    errors = []
    for raw in paths:
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
            errors.extend(problems)
        else:
            print(f"pasteguard scan: not a file or directory: {raw}", file=sys.stderr)
            return 2

    try:
        allow = _load_allowlist()
    except SystemExit as ex:
        message = ex.code
        if isinstance(message, str) and message.strip():
            print(message.strip(), file=sys.stderr)
        return 2
    except Exception as ex:
        if type(ex).__name__ == "TOMLDecodeError":
            print(f"pasteguard scan: {ex}", file=sys.stderr)
            return 2
        raise

    stdin_text = None
    stdin_done = False
    if any(item is None for item in planned):
        stdin_text = _read_stdin()

    records: list[dict] = []
    files = 0
    allowlisted = 0
    seen = set()
    for item in planned:
        if item is None:
            if stdin_done:
                continue
            stdin_done = True
            if stdin_text is None:
                continue
            rows, dropped = _scan_one("-", stdin_text, allow)
            files += 1
            allowlisted += dropped
            records.extend(rows)
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
        rows, dropped = _scan_one(display, text, allow)
        files += 1
        allowlisted += dropped
        records.extend(rows)

    for message in errors:
        print(f"pasteguard scan: {message}", file=sys.stderr)
    records.sort(key=lambda rec: (rec["path"], rec["line"], rec["col"], rec["rule"]))
    block = sum(1 for rec in records if rec["severity"] == "block")
    coach = sum(1 for rec in records if rec["severity"] == "coach")
    _emit(records, _summary(files, len(records), block, coach, allowlisted), args.format)
    if errors:
        return 2
    if args.fail_on == "coach":
        return 1 if block or coach else 0
    return 1 if block else 0


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
