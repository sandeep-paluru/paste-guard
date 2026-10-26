"""Custom [[scan.rules]] detectors for pasteguard scan. No model and no index."""
import hashlib
import json
import math
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from secrets_scan import RULES, _CUSTOM_LINE_CAP, severity  # noqa: E402

SCAN = [sys.executable, str(ROOT / "backend" / "secrets_scan.py"), "scan"]

INNER = "Ab3dEf7hJk2mNp5qRs8tUv1wXy4z0291"
OTHER = "m7n6b5v4c3x2z1l0k9j8h7g6f5d4s3a2"
THIRD = "Qw1Er2Ty3Ui4Op5As6Df7Gh8Jk9Lz0Xc"
LOW = "a" * 32
HIGH = "abcdefghijklmnopqrstuvwxyz012345"
TOKEN = "acme_live_" + INNER
TOKEN_B = "acme_live_" + OTHER
TOKEN_C = "acme_live_" + THIRD
VENDOR = "vendor_tok_" + OTHER
NOTE = "acme_note_" + INNER
KEY = "AKIA" + "0123456789ABCDEF"


def _env(**extra):
    env = os.environ.copy()
    env["PG_SECRETS_EXAMPLES"] = "0"
    env.pop("PG_SECRETS_ALLOWLIST", None)
    env.pop("PG_CONFIG", None)
    env.update({k: v for k, v in extra.items() if v is not None})
    for key, value in extra.items():
        if value is None:
            env.pop(key, None)
    return env


def scan(args, *, input=None, env=None, cwd=None):
    return subprocess.run(
        SCAN + list(args),
        input=input,
        capture_output=True,
        cwd=cwd,
        env=_env(**(env or {})),
    )


def hidden(secret, proc):
    out = proc.stdout.decode() + "\n" + proc.stderr.decode()
    assert secret not in out
    if len(secret) > 4:
        assert secret[4:] not in out


def summary_of(proc, fmt="text"):
    blob = proc.stderr if fmt in ("json", "sarif") else proc.stdout
    line = blob.decode().strip().splitlines()[-1]
    assert line.startswith("scanned "), line
    return line


def entropy(value):
    counts = {}
    for ch in value:
        counts[ch] = counts.get(ch, 0) + 1
    total = len(value)
    return -sum((count / total) * math.log2(count / total) for count in counts.values())


def _fingerprint(rule, value):
    return hashlib.sha256(rule.encode() + b"\0" + value.encode()).hexdigest()


def git(repo, *args):
    env = os.environ.copy()
    env.update({
        "GIT_AUTHOR_NAME": "Test User",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "Test User",
        "GIT_COMMITTER_EMAIL": "test@example.com",
    })
    proc = subprocess.run(
        ["git", "-c", "commit.gpgsign=false", *args],
        cwd=repo, env=env, capture_output=True,
    )
    if proc.returncode != 0:
        raise AssertionError((args, proc.stdout.decode(), proc.stderr.decode()))
    return proc


def init_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-b", "main")
    git(path, "config", "core.autocrlf", "false")
    return path


def commit_all(repo, message="msg"):
    git(repo, "add", "-A")
    git(repo, "commit", "-m", message)


def _rule(name, regex, severity_name, **fields):
    lines = [
        "[[scan.rules]]",
        f'name = "{name}"',
        f"regex = '{regex}'",
        f'severity = "{severity_name}"',
    ]
    for key, value in fields.items():
        if isinstance(value, str):
            lines.append(f'{key} = "{value}"')
        elif isinstance(value, list):
            rendered = ", ".join(f'"{item}"' for item in value)
            lines.append(f"{key} = [{rendered}]")
        elif isinstance(value, bool):
            lines.append(f"{key} = {'true' if value else 'false'}")
        else:
            lines.append(f"{key} = {value}")
    return "\n".join(lines) + "\n"


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_list_rules_prints_builtin_and_custom(tmp_path):
    cfg = _write(tmp_path / "paste-guard.toml", _rule(
        "acme_live", "acme_live_([A-Za-z0-9]{32})", "block",
        description="Acme live API token",
    ))
    extra = _write(tmp_path / "more.toml", _rule(
        "acme_note", "acme_note_([A-Za-z0-9]{32})", "coach",
        description="Acme note token",
    ))
    # A secret sitting in the work tree must not be scanned, and stdin must not be read.
    _write(tmp_path / "secret.txt", TOKEN + "\n")
    proc = scan(
        ["--list-rules", "--rules", extra.name],
        cwd=tmp_path,
        input=b"",
        env={"PG_CONFIG": str(cfg)},
    )
    assert proc.returncode == 0, proc.stderr.decode()
    lines = proc.stdout.decode().splitlines()
    assert lines[:len(RULES)] == [f"{name} {severity(name)} built-in" for name in RULES]
    assert lines[len(RULES):] == [
        "acme_live block paste-guard.toml",
        "acme_note coach more.toml",
    ]
    assert "scanned" not in proc.stdout.decode()
    assert TOKEN not in proc.stdout.decode()
    hidden(INNER, proc)

    bare = scan(["--list-rules"], cwd=tmp_path, input=b"")
    assert bare.returncode == 0
    assert bare.stdout.decode().splitlines() == [f"{name} {severity(name)} built-in" for name in RULES]

    paths = scan(["--list-rules", "secret.txt"], cwd=tmp_path)
    assert paths.returncode == 2
    assert b"--list-rules does not take path arguments" in paths.stderr
    assert b"acme_live" not in paths.stdout


def test_rule_validation_errors(tmp_path):
    _write(tmp_path / "key.txt", KEY + "\n")

    bad_re = _write(tmp_path / "badre.toml", _rule(
        "acme_live", "acme_live_([A-Za-z0-9]{32}", "block",
    ))
    proc = scan(["--rules", str(bad_re), "key.txt"], cwd=tmp_path)
    assert proc.returncode == 2
    err = proc.stderr.decode()
    assert "rule acme_live" in err and "bad regex" in err
    assert proc.stdout == b""
    assert b"aws_access_key" not in proc.stdout
    hidden(KEY, proc)

    dup = _write(tmp_path / "dup.toml", _rule(
        "acme_live", "acme_live_[A-Za-z0-9]{32}", "block",
    ) + _rule("acme_live", "acme_live_[A-Za-z0-9]{16}", "coach"))
    proc = scan(["--rules", str(dup), "--list-rules"], cwd=tmp_path, input=b"")
    assert proc.returncode == 2
    assert "rule acme_live" in proc.stderr.decode() and "duplicate name" in proc.stderr.decode()
    assert proc.stdout == b""

    cfg = _write(tmp_path / "paste-guard.toml", _rule(
        "acme_live", "acme_live_[A-Za-z0-9]{32}", "block",
    ))
    again = _write(tmp_path / "again.toml", _rule(
        "acme_live", "acme_live_[A-Za-z0-9]{32}", "block",
    ))
    proc = scan(["--rules", str(again), "--list-rules"], cwd=tmp_path, input=b"", env={"PG_CONFIG": str(cfg)})
    assert proc.returncode == 2
    err = proc.stderr.decode()
    assert "rule acme_live" in err and "duplicate name" in err and "again.toml" in err

    clash = _write(tmp_path / "clash.toml", _rule(
        "aws_access_key", "AKIA[0-9A-Z]{16}", "block",
    ))
    proc = scan(["--rules", str(clash), "key.txt"], cwd=tmp_path)
    assert proc.returncode == 2
    err = proc.stderr.decode()
    assert "rule aws_access_key" in err and "built-in" in err
    assert b"aws_access_key block" not in proc.stdout

    sev = _write(tmp_path / "sev.toml", _rule(
        "acme_live", "acme_live_[A-Za-z0-9]{32}", "warn",
    ))
    proc = scan(["--rules", str(sev), "key.txt"], cwd=tmp_path)
    assert proc.returncode == 2
    err = proc.stderr.decode()
    assert "rule acme_live" in err and "unknown severity" in err and "warn" in err

    group = _write(tmp_path / "group.toml", _rule(
        "acme_live", "acme_live_([A-Za-z0-9]{32})", "block", secret_group=3,
    ))
    proc = scan(["--rules", str(group), "key.txt"], cwd=tmp_path)
    assert proc.returncode == 2
    err = proc.stderr.decode()
    assert "rule acme_live" in err and "secret_group 3" in err and "out of range" in err

    missing = _write(tmp_path / "missing.toml", '[[scan.rules]]\nregex = "abc"\nseverity = "block"\n')
    proc = scan(["--rules", str(missing), "--list-rules"], cwd=tmp_path, input=b"")
    assert proc.returncode == 2
    assert "scan.rules[0]" in proc.stderr.decode() and "missing name" in proc.stderr.decode()

    broken = _write(tmp_path / "broken.toml", "[[scan.rules]\nname = \"acme_live\"\n")
    proc = scan(["--rules", str(broken), "key.txt"], cwd=tmp_path)
    assert proc.returncode == 2
    assert "not valid TOML" in proc.stderr.decode()
    assert "broken.toml" in proc.stderr.decode()

    absent = scan(["--rules", str(tmp_path / "nope.toml"), "key.txt"], cwd=tmp_path)
    assert absent.returncode == 2
    assert "rules file not found" in absent.stderr.decode()

    words = _write(tmp_path / "words.toml", _rule(
        "acme_live", "acme_live_[A-Za-z0-9]{32}", "block",
    ).replace('severity = "block"\n', 'severity = "block"\nkeywords = "acme_live_"\n'))
    proc = scan(["--rules", str(words), "key.txt"], cwd=tmp_path)
    assert proc.returncode == 2
    assert "rule acme_live" in proc.stderr.decode() and "keywords must be a list of strings" in proc.stderr.decode()


def test_custom_rule_text_json_sarif(tmp_path):
    cfg = _write(tmp_path / "paste-guard.toml", _rule(
        "acme_live", "acme_live_([A-Za-z0-9]{32})", "block",
        keywords=["acme_live_"], secret_group=1, description="Acme live API token",
    ))
    extra = _write(tmp_path / "more.toml", _rule(
        "vendor_tok", "vendor_tok_([A-Za-z0-9]{32})", "block",
        secret_group=1, description="Vendor token",
    ) + _rule(
        "acme_note", "acme_note_([A-Za-z0-9]{32})", "coach",
        description="Acme note token",
    ))
    body = "xx" + TOKEN + "\n" + VENDOR + "\n"
    _write(tmp_path / "keys.txt", body)
    env = {"PG_CONFIG": str(cfg)}
    args = ["--rules", extra.name]

    text = scan(args + ["keys.txt"], cwd=tmp_path, env=env)
    assert text.returncode == 1
    out = text.stdout.decode()
    assert f"keys.txt:1:3 acme_live block {INNER[:4]}({len(INNER)})" in out
    assert f"keys.txt:2:1 vendor_tok block {OTHER[:4]}({len(OTHER)})" in out
    assert "acme_note" not in out
    assert summary_of(text) == "scanned 1 file, 2 findings, 2 block, 0 coach, 0 allowlisted, 0 inline"
    hidden(TOKEN, text)
    hidden(INNER, text)
    hidden(VENDOR, text)
    hidden(OTHER, text)

    proc = scan(args + ["keys.txt", "--format", "json"], cwd=tmp_path, env=env)
    assert proc.returncode == 1
    rows = json.loads(proc.stdout)
    assert rows == [
        {"path": "keys.txt", "line": 1, "col": 3, "rule": "acme_live", "severity": "block",
         "mask": f"{INNER[:4]}({len(INNER)})", "length": len(INNER)},
        {"path": "keys.txt", "line": 2, "col": 1, "rule": "vendor_tok", "severity": "block",
         "mask": f"{OTHER[:4]}({len(OTHER)})", "length": len(OTHER)},
    ]
    hidden(TOKEN, proc)
    hidden(INNER, proc)
    hidden(VENDOR, proc)
    assert summary_of(proc, "json") == summary_of(text)
    assert "allowlisted" not in proc.stdout.decode()

    sarif = scan(args + ["keys.txt", "--format", "sarif"], cwd=tmp_path, env=env)
    assert sarif.returncode == 1
    doc = json.loads(sarif.stdout)
    driver = doc["runs"][0]["tool"]["driver"]
    ids = [rule["id"] for rule in driver["rules"]]
    assert ids == list(RULES) + ["acme_live", "vendor_tok", "acme_note"]
    by_id = {rule["id"]: rule for rule in driver["rules"]}
    assert by_id["acme_live"]["shortDescription"]["text"] == "Acme live API token"
    assert by_id["acme_live"]["defaultConfiguration"]["level"] == "error"
    assert by_id["vendor_tok"]["shortDescription"]["text"] == "Vendor token"
    assert by_id["acme_note"]["shortDescription"]["text"] == "Acme note token"
    assert by_id["acme_note"]["defaultConfiguration"]["level"] == "warning"
    results = doc["runs"][0]["results"]
    assert [row["ruleId"] for row in results] == ["acme_live", "vendor_tok"]
    assert results[0]["ruleIndex"] == ids.index("acme_live")
    assert results[0]["level"] == "error"
    assert results[0]["message"]["text"] == f"{INNER[:4]}({len(INNER)})"
    region = results[0]["locations"][0]["physicalLocation"]["region"]
    assert region == {"startLine": 1, "startColumn": 3}
    hidden(TOKEN, sarif)
    hidden(INNER, sarif)
    hidden(VENDOR, sarif)
    hidden(OTHER, sarif)
    assert summary_of(sarif, "sarif") == summary_of(text)

    piped = scan(args, input=body.encode(), cwd=tmp_path, env=env)
    assert piped.returncode == 1
    assert piped.stdout.decode().splitlines()[0].startswith(f"-:1:3 acme_live block {INNER[:4]}(")
    hidden(INNER, piped)

    # Config alone, with no --rules file, still loads [[scan.rules]].
    only = scan(["keys.txt"], cwd=tmp_path, env=env)
    assert only.returncode == 1
    assert "acme_live" in only.stdout.decode()
    assert "vendor_tok" not in only.stdout.decode()
    hidden(TOKEN, only)
    hidden(VENDOR, only)


def test_coach_rule_and_fail_on(tmp_path):
    rules = _write(tmp_path / "rules.toml", _rule(
        "acme_note", "acme_note_([A-Za-z0-9]{32})", "coach",
        secret_group=1, description="Acme note token",
    ))
    _write(tmp_path / "note.txt", NOTE + "\n")
    proc = scan(["--rules", rules.name, "note.txt"], cwd=tmp_path)
    assert proc.returncode == 0
    assert f"note.txt:1:1 acme_note coach {INNER[:4]}({len(INNER)})" in proc.stdout.decode()
    hidden(NOTE, proc)
    hidden(INNER, proc)

    strict = scan(["--rules", rules.name, "--fail-on", "coach", "note.txt"], cwd=tmp_path)
    assert strict.returncode == 1
    hidden(NOTE, strict)

    sarif = scan(["--rules", rules.name, "--format", "sarif", "note.txt"], cwd=tmp_path)
    assert sarif.returncode == 0
    doc = json.loads(sarif.stdout)
    row = doc["runs"][0]["results"][0]
    assert row["ruleId"] == "acme_note" and row["level"] == "warning"
    assert row["message"]["text"] == f"{INNER[:4]}({len(INNER)})"
    hidden(NOTE, sarif)
    hidden(INNER, sarif)


def test_keyword_prefilter(tmp_path):
    rules = _write(tmp_path / "rules.toml", _rule(
        "wide", "[A-Za-z0-9]{32}", "block", keywords=["acme_live_"],
    ))
    text = "\n".join([HIGH, "acme_live_ " + HIGH, "ACME_LIVE_ " + HIGH, ""])
    _write(tmp_path / "keys.txt", text)
    proc = scan(["--rules", rules.name, "keys.txt"], cwd=tmp_path)
    assert proc.returncode == 1
    out = proc.stdout.decode()
    assert f"keys.txt:2:12 wide block {HIGH[:4]}({len(HIGH)})" in out
    assert f"keys.txt:3:12 wide block {HIGH[:4]}({len(HIGH)})" in out
    assert "keys.txt:1:" not in out
    assert summary_of(proc) == "scanned 1 file, 2 findings, 2 block, 0 coach, 0 allowlisted, 0 inline"
    hidden(HIGH, proc)


def test_entropy_floor(tmp_path):
    # The repeated capture is below the floor. The whole match is above it, so
    # a floor applied to the wrong string would keep the first line.
    assert entropy(LOW) < 1.0 <= entropy("acme_live_" + LOW)
    rules = _write(tmp_path / "rules.toml", _rule(
        "acme_live", "acme_live_([A-Za-z0-9]{32})", "block",
        secret_group=1, min_entropy=1.0,
    ))
    _write(tmp_path / "keys.txt", "acme_live_" + LOW + "\nacme_live_" + HIGH + "\n")
    proc = scan(["--rules", rules.name, "keys.txt"], cwd=tmp_path)
    assert proc.returncode == 1
    out = proc.stdout.decode()
    assert f"keys.txt:2:1 acme_live block {HIGH[:4]}({len(HIGH)})" in out
    assert "keys.txt:1:" not in out
    assert summary_of(proc) == "scanned 1 file, 1 finding, 1 block, 0 coach, 0 allowlisted, 0 inline"
    hidden(LOW, proc)
    hidden(HIGH, proc)
    hidden("acme_live_" + LOW, proc)
    hidden("acme_live_" + HIGH, proc)


def test_allowlist_baseline_and_inline(tmp_path):
    rules = _write(tmp_path / "rules.toml", _rule(
        "acme_live", "acme_live_([A-Za-z0-9]{32})", "block", secret_group=1,
    ))
    listed = _write(tmp_path / "allow.txt", "value:" + INNER + "\n")
    _write(tmp_path / "safe.txt", TOKEN + "\n")
    safe = scan(
        ["--rules", rules.name, "safe.txt"],
        cwd=tmp_path,
        env={"PG_SECRETS_ALLOWLIST": str(listed)},
    )
    assert safe.returncode == 0
    assert "acme_live" not in safe.stdout.decode()
    assert summary_of(safe) == "scanned 1 file, 0 findings, 0 block, 0 coach, 1 allowlisted, 0 inline"
    hidden(TOKEN, safe)
    hidden(INNER, safe)

    _write(tmp_path / "mix.txt", "\n".join([
        TOKEN,
        TOKEN_B + "  # pasteguard:ignore=acme_live",
        TOKEN_C + "  # pasteguard:ignore=aws_access_key",
        "# pasteguard:ignore=acme_live",
        "",
    ]))
    base = tmp_path / "baseline.json"
    base.write_text(json.dumps({
        "version": 1,
        "findings": [{
            "path": "mix.txt",
            "rule": "acme_live",
            "fingerprint": _fingerprint("acme_live", INNER),
        }],
    }) + "\n", encoding="utf-8")
    proc = scan(
        ["--rules", rules.name, "--baseline", str(base), "--report-unused-ignores", "mix.txt"],
        cwd=tmp_path,
    )
    assert proc.returncode == 1
    out = proc.stdout.decode()
    assert f"mix.txt:3:1 acme_live block {THIRD[:4]}({len(THIRD)})" in out
    assert "mix.txt:1:" not in out
    assert "mix.txt:2:" not in out.split("unused")[0]
    assert "mix.txt:4 unused pasteguard:ignore" in out
    assert summary_of(proc) == (
        "scanned 1 file, 1 finding, 1 block, 0 coach, 0 allowlisted, 1 inline, 1 suppressed"
    )
    assert "unknown rule" not in proc.stderr.decode()
    hidden(TOKEN, proc)
    hidden(TOKEN_B, proc)
    hidden(TOKEN_C, proc)
    hidden(INNER, proc)
    hidden(OTHER, proc)
    hidden(THIRD, proc)

    # The fingerprint is the captured group, and the raw value is not stored.
    first = scan(["--rules", rules.name, "--write-baseline", str(base), "safe.txt"], cwd=tmp_path)
    assert first.returncode == 1
    stored = json.loads(base.read_text(encoding="utf-8"))
    assert stored["findings"] == [{
        "path": "safe.txt",
        "rule": "acme_live",
        "fingerprint": _fingerprint("acme_live", INNER),
    }]
    hidden(TOKEN, first)
    assert INNER not in base.read_text(encoding="utf-8")
    assert TOKEN not in base.read_text(encoding="utf-8")

    second = scan(["--rules", rules.name, "--baseline", str(base), "safe.txt"], cwd=tmp_path)
    assert second.returncode == 0
    assert "acme_live" not in second.stdout.decode()
    assert summary_of(second).endswith("0 allowlisted, 0 inline, 1 suppressed")
    hidden(TOKEN, second)
    hidden(INNER, second)


def test_custom_rules_on_added_lines(tmp_path):
    rules = _write(tmp_path / "rules.toml", _rule(
        "acme_live", "acme_live_[A-Za-z0-9]{32}", "block",
    ))
    repo = init_repo(tmp_path / "repo")
    _write(repo / "app.txt", "old " + TOKEN + "\n")
    commit_all(repo, "init")
    _write(repo / "app.txt", "\n".join([
        "old " + TOKEN,
        TOKEN_B + "  # pasteguard:ignore=acme_live",
        "new " + TOKEN_C,
        "",
    ]))
    git(repo, "add", "app.txt")

    staged = scan(["--staged", "--rules", str(rules)], cwd=repo)
    assert staged.returncode == 1, staged.stderr.decode()
    body = staged.stdout.decode()
    assert f"app.txt:3:5 acme_live block {TOKEN_C[:4]}({len(TOKEN_C)})" in body
    assert "app.txt:1:" not in body
    assert "app.txt:2:" not in body
    assert "unknown rule" not in staged.stderr.decode()
    assert summary_of(staged) == "scanned 1 file, 1 finding, 1 block, 0 coach, 0 allowlisted, 1 inline"
    hidden(TOKEN, staged)
    hidden(TOKEN_B, staged)
    hidden(TOKEN_C, staged)

    git(repo, "checkout", "-b", "feature")
    git(repo, "commit", "-m", "add")
    diff = scan(["--diff-base", "main", "--rules", str(rules), "--format", "json"], cwd=repo)
    assert diff.returncode == 1, diff.stderr.decode()
    rows = json.loads(diff.stdout)
    assert rows == [{
        "path": "app.txt", "line": 3, "col": 5, "rule": "acme_live", "severity": "block",
        "mask": f"{TOKEN_C[:4]}({len(TOKEN_C)})", "length": len(TOKEN_C),
    }]
    assert summary_of(diff, "json") == summary_of(staged)
    hidden(TOKEN, diff)
    hidden(TOKEN_B, diff)
    hidden(TOKEN_C, diff)


def test_long_lines_are_capped(tmp_path):
    rules = _write(tmp_path / "rules.toml", _rule(
        "acme_live", "acme_live_[A-Za-z0-9]{32}", "block",
    ))
    pad = "b" * _CUSTOM_LINE_CAP
    _write(tmp_path / "early.txt", TOKEN + pad + "\n")
    _write(tmp_path / "late.txt", pad + TOKEN + "\n")
    early = scan(["--rules", rules.name, "early.txt"], cwd=tmp_path)
    assert early.returncode == 1
    assert f"early.txt:1:1 acme_live block {TOKEN[:4]}({len(TOKEN)})" in early.stdout.decode()
    hidden(TOKEN, early)
    late = scan(["--rules", rules.name, "late.txt"], cwd=tmp_path)
    assert late.returncode == 0
    assert "acme_live" not in late.stdout.decode()
    assert summary_of(late) == "scanned 1 file, 0 findings, 0 block, 0 coach, 0 allowlisted, 0 inline"
    hidden(TOKEN, late)


def test_custom_rule_beats_password_assignment(tmp_path):
    rules = _write(tmp_path / "rules.toml", _rule(
        "acme_live", "acme_live_[A-Za-z0-9]{32}", "block",
    ))
    _write(tmp_path / "app.py", "API_KEY=" + TOKEN + "\n")
    proc = scan(["--rules", rules.name, "app.py"], cwd=tmp_path)
    assert proc.returncode == 1
    body = proc.stdout.decode()
    assert f"app.py:1:9 acme_live block {TOKEN[:4]}({len(TOKEN)})" in body
    assert "password_assignment" not in body
    assert summary_of(proc) == "scanned 1 file, 1 finding, 1 block, 0 coach, 0 allowlisted, 0 inline"
    hidden(TOKEN, proc)


def test_builtin_wins_equal_span(tmp_path):
    rules = _write(
        tmp_path / "rules.toml",
        "[[scan.rules]]\n"
        'name = "aws_shaped"\n'
        "regex = '\\bAKIA[0-9A-Z]{16}\\b'\n"
        'severity = "block"\n',
    )
    _write(tmp_path / "key.txt", KEY + "\n")
    proc = scan(["--rules", rules.name, "key.txt"], cwd=tmp_path)
    assert proc.returncode == 1
    body = proc.stdout.decode()
    assert f"key.txt:1:1 aws_access_key block {KEY[:4]}({len(KEY)})" in body
    assert "aws_shaped" not in body
    assert summary_of(proc) == "scanned 1 file, 1 finding, 1 block, 0 coach, 0 allowlisted, 0 inline"
    hidden(KEY, proc)
