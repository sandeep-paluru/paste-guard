"""pasteguard scan: files, stdin, allowlist, exit codes. No model and no index."""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from secrets_scan import RULES, RULE_DESCRIPTIONS, public_examples, severity  # noqa: E402

SCAN = [sys.executable, str(ROOT / "backend" / "secrets_scan.py"), "scan"]


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


def _walk_strings(obj):
    if isinstance(obj, dict):
        for value in obj.values():
            yield from _walk_strings(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from _walk_strings(value)
    else:
        yield str(obj)


KEY = "AKIA" + "0123456789ABCDEF"
HF = "hf_" + ("A" * 34)


def test_line_column_and_mask_text_and_json(tmp_path):
    content = "é " + KEY + "\r\n\n  " + HF + "\n"
    (tmp_path / "keys.txt").write_text(content, encoding="utf-8")
    # The fixture's own line breaks, checked without the scanner's locator.
    lines = content.splitlines()
    assert lines[0].index(KEY) + 1 == 3
    assert lines[2].index(HF) + 1 == 3

    text = scan(["keys.txt"], cwd=tmp_path)
    assert text.returncode == 1
    body = text.stdout.decode()
    assert f"keys.txt:1:3 aws_access_key block {KEY[:4]}({len(KEY)})" in body
    assert f"keys.txt:3:3 huggingface_token block {HF[:4]}({len(HF)})" in body
    assert summary_of(text) == "scanned 1 file, 2 findings, 2 block, 0 coach, 0 allowlisted"
    hidden(KEY, text)
    hidden(HF, text)

    proc = scan(["keys.txt", "--format", "json"], cwd=tmp_path)
    assert proc.returncode == 1
    rows = json.loads(proc.stdout)
    assert rows == [
        {"path": "keys.txt", "line": 1, "col": 3, "rule": "aws_access_key", "severity": "block",
         "mask": f"{KEY[:4]}({len(KEY)})", "length": len(KEY)},
        {"path": "keys.txt", "line": 3, "col": 3, "rule": "huggingface_token", "severity": "block",
         "mask": f"{HF[:4]}({len(HF)})", "length": len(HF)},
    ]
    for value in _walk_strings(rows):
        assert KEY not in value and HF not in value
        assert KEY[4:] not in value and HF[4:] not in value
    hidden(KEY, proc)
    hidden(HF, proc)
    assert summary_of(proc, "json") == summary_of(text)
    # stdout is only the list, so a JSON parser does not see the summary line
    assert "allowlisted" not in proc.stdout.decode()
    assert "allowlisted" in proc.stderr.decode()


def test_password_and_database_url_are_masked(tmp_path):
    pw = "correct" + "horse"
    db_pw = "s3cret" + "-token"
    url = "postgres://user:" + db_pw + "@db.example.com/app"
    (tmp_path / "quote.txt").write_text('password = "' + pw + '"\n', encoding="utf-8")
    (tmp_path / "db.txt").write_text(url + "\n", encoding="utf-8")

    for fmt in ("text", "json"):
        quote = scan(["quote.txt", "--format", fmt], cwd=tmp_path)
        assert quote.returncode == 0  # password assignments coach
        hidden(pw, quote)
        if fmt == "json":
            row = json.loads(quote.stdout)[0]
            assert row["rule"] == "password_assignment" and row["severity"] == "coach"
            assert row["mask"] == f"{pw[:4]}({len(pw)})" and row["length"] == len(pw)
            assert row["line"] == 1 and row["col"] == 1
        else:
            assert f"password_assignment coach {pw[:4]}({len(pw)})" in quote.stdout.decode()

        db = scan(["db.txt", "--format", fmt], cwd=tmp_path)
        assert db.returncode == 1
        hidden(db_pw, db)
        hidden(url, db)
        if fmt == "json":
            row = json.loads(db.stdout)[0]
            assert row["rule"] == "db_url_password" and row["severity"] == "block"
            assert row["mask"] == f"{db_pw[:4]}({len(db_pw)})"
        else:
            assert f"db_url_password block {db_pw[:4]}({len(db_pw)})" in db.stdout.decode()


def test_specific_rule_wins_on_overlap(tmp_path):
    key = "sk-ant-" + "api03-" + ("Ab3dE" * 18) + "-xyzAA"
    (tmp_path / "app.py").write_text('api_key="' + key + '"\n', encoding="utf-8")
    proc = scan(["app.py"], cwd=tmp_path)
    assert proc.returncode == 1
    body = proc.stdout.decode()
    assert "app.py:1:10 anthropic_key block" in body
    assert "password_assignment" not in body
    hidden(key, proc)
    js = scan(["app.py", "--format", "json"], cwd=tmp_path)
    rows = json.loads(js.stdout)
    assert rows[0]["rule"] == "anthropic_key" and rows[0]["col"] == 10
    hidden(key, js)


def test_allowlisted_values_do_not_fail(tmp_path):
    key = KEY
    near = key[:-1] + "Z"
    listed = tmp_path / "allow.txt"
    listed.write_text("value:" + key + "\n", encoding="utf-8")
    (tmp_path / "safe.txt").write_text(key + "\n", encoding="utf-8")
    (tmp_path / "near.txt").write_text(near + "\n", encoding="utf-8")
    env = {"PG_SECRETS_ALLOWLIST": str(listed)}

    safe = scan(["safe.txt"], cwd=tmp_path, env=env)
    assert safe.returncode == 0
    hidden(key, safe)
    assert summary_of(safe) == "scanned 1 file, 0 findings, 0 block, 0 coach, 1 allowlisted"
    js = scan(["safe.txt", "--format", "json"], cwd=tmp_path, env=env)
    assert js.returncode == 0
    assert json.loads(js.stdout) == []
    hidden(key, js)
    assert summary_of(js, "json").endswith("1 allowlisted")

    near_proc = scan(["near.txt"], cwd=tmp_path, env=env)
    assert near_proc.returncode == 1
    hidden(near, near_proc)
    assert summary_of(near_proc).endswith("0 allowlisted")

    pw = "hunter2" + "-prod-9x"
    digest = hashlib.sha256(pw.encode()).hexdigest()
    (tmp_path / "sha.txt").write_text("sha256:" + digest + "\n", encoding="utf-8")
    (tmp_path / ".env").write_text("DB_PASSWORD=" + pw + "\n", encoding="utf-8")
    hashed = scan([".env"], cwd=tmp_path, env={"PG_SECRETS_ALLOWLIST": str(tmp_path / "sha.txt")})
    assert hashed.returncode == 0
    hidden(pw, hashed)
    assert summary_of(hashed).endswith("1 allowlisted")

    akia = public_examples()[0]
    (tmp_path / "doc.txt").write_text("sample " + akia + "\n", encoding="utf-8")
    on = scan(["doc.txt"], cwd=tmp_path, env={"PG_SECRETS_EXAMPLES": "1"})
    assert on.returncode == 0
    hidden(akia, on)
    assert "1 allowlisted" in summary_of(on)
    off = scan(["doc.txt"], cwd=tmp_path, env={"PG_SECRETS_EXAMPLES": "0"})
    assert off.returncode == 1
    hidden(akia, off)
    assert "0 allowlisted" in summary_of(off)

    cfg = tmp_path / "paste-guard.toml"
    cfg.write_text('[secrets]\nexamples = false\nallowlist = ["value:' + key + '"]\n', encoding="utf-8")
    toml = scan(["safe.txt"], cwd=tmp_path, env={"PG_CONFIG": str(cfg), "PG_SECRETS_EXAMPLES": None})
    assert toml.returncode == 0
    hidden(key, toml)
    assert summary_of(toml).endswith("1 allowlisted")


def test_exit_codes(tmp_path):
    (tmp_path / "clean.txt").write_text("hello\n", encoding="utf-8")
    (tmp_path / "also.txt").write_text("world\n", encoding="utf-8")
    clean = scan(["clean.txt", "also.txt"], cwd=tmp_path)
    assert clean.returncode == 0
    assert summary_of(clean) == "scanned 2 files, 0 findings, 0 block, 0 coach, 0 allowlisted"

    (tmp_path / "key.txt").write_text(KEY + "\n", encoding="utf-8")
    assert scan(["key.txt"], cwd=tmp_path).returncode == 1

    empty = tmp_path / "empty"
    empty.mkdir()
    none = scan([str(empty)])
    assert none.returncode == 0
    assert summary_of(none) == "scanned 0 files, 0 findings, 0 block, 0 coach, 0 allowlisted"

    assert scan(["--bogus"]).returncode == 2
    assert scan(["--fail-on"]).returncode == 2
    assert scan(["--fail-on", "nudge"]).returncode == 2
    assert scan(["--format", "xml"]).returncode == 2
    missing = scan([str(tmp_path / "nope.txt")])
    assert missing.returncode == 2
    assert b"not found" in missing.stderr

    bad_list = scan(["clean.txt"], cwd=tmp_path, env={"PG_SECRETS_ALLOWLIST": str(tmp_path / "missing.txt")})
    assert bad_list.returncode == 2
    assert b"not found" in bad_list.stderr

    bad_toml = tmp_path / "bad.toml"
    bad_toml.write_text("[secrets\n", encoding="utf-8")
    broken = scan(["clean.txt"], cwd=tmp_path, env={"PG_CONFIG": str(bad_toml)})
    assert broken.returncode == 2

    help_proc = scan(["--help"])
    assert help_proc.returncode == 0
    assert b"pasteguard scan" in help_proc.stdout


def test_fail_on_coach(tmp_path):
    pw = "hunter2" + "-prod-9x"
    jwt = (
        "eyJ" + "hbGciOiJIUzI1NiJ9."
        + "eyJ" + "zdWIiOiIxMjM0NTY3ODkwIn0."
        + "dozjgNryP4J3jVmNHl0w5N"
    )
    (tmp_path / ".env").write_text("DB_PASSWORD=" + pw + "\n" + jwt + "\n", encoding="utf-8")
    base = scan([".env"], cwd=tmp_path)
    assert base.returncode == 0
    body = base.stdout.decode()
    assert f".env:1:1 password_assignment coach {pw[:4]}({len(pw)})" in body
    assert f".env:2:1 jwt coach {jwt[:4]}({len(jwt)})" in body
    assert summary_of(base) == "scanned 1 file, 2 findings, 0 block, 2 coach, 0 allowlisted"
    hidden(pw, base)
    hidden(jwt, base)

    fail = scan(["--fail-on", "coach", ".env"], cwd=tmp_path)
    assert fail.returncode == 1
    hidden(pw, fail)
    hidden(jwt, fail)

    (tmp_path / "key.txt").write_text(KEY + "\n", encoding="utf-8")
    assert scan(["--fail-on", "coach", "key.txt"], cwd=tmp_path).returncode == 1
    (tmp_path / "clean.txt").write_text("hello\n", encoding="utf-8")
    assert scan(["--fail-on", "coach", "clean.txt"], cwd=tmp_path).returncode == 0


def test_exclude(tmp_path):
    (tmp_path / "keep.txt").write_text("hello\n", encoding="utf-8")
    (tmp_path / "noise.txt").write_text(KEY + "\n", encoding="utf-8")
    drop = tmp_path / "drop"
    drop.mkdir()
    (drop / "hide.txt").write_text(KEY + "\n", encoding="utf-8")

    kept = scan(["--exclude", "drop/*", "--exclude", "noise.txt", "."], cwd=tmp_path)
    assert kept.returncode == 0
    hidden(KEY, kept)
    assert "noise.txt" not in kept.stdout.decode()
    assert "hide.txt" not in kept.stdout.decode()
    assert summary_of(kept) == "scanned 1 file, 0 findings, 0 block, 0 coach, 0 allowlisted"

    bare = scan(["."], cwd=tmp_path)
    assert bare.returncode == 1
    assert summary_of(bare) == "scanned 3 files, 2 findings, 2 block, 0 coach, 0 allowlisted"
    hidden(KEY, bare)


def test_vendor_dirs_skipped(tmp_path):
    for folder in (".git", "node_modules/pkg", "vendor", ".venv", ".pytest_cache"):
        path = tmp_path.joinpath(*folder.split("/"))
        path.mkdir(parents=True)
        (path / "secret.txt").write_text(KEY + "\n", encoding="utf-8")
    gh = tmp_path / ".github" / "workflows"
    gh.mkdir(parents=True)
    (gh / "ci.yml").write_text(KEY + "\n", encoding="utf-8")
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text("x = 1\n" + KEY + "\n", encoding="utf-8")

    proc = scan(["."], cwd=tmp_path)
    assert proc.returncode == 1
    body = proc.stdout.decode()
    assert ".github/workflows/ci.yml:1:1 aws_access_key block" in body
    assert "src/app.py:2:1 aws_access_key block" in body
    for skipped in ("node_modules/", ".git/", "vendor/", ".venv/", ".pytest_cache/"):
        assert skipped not in body
        assert skipped not in proc.stderr.decode()
    hidden(KEY, proc)
    assert summary_of(proc) == "scanned 2 files, 2 findings, 2 block, 0 coach, 0 allowlisted"


def test_stdin(tmp_path):
    proc = scan([], input=(KEY + "\n").encode())
    assert proc.returncode == 1
    assert proc.stdout.decode().startswith(f"-:1:1 aws_access_key block {KEY[:4]}({len(KEY)})")
    hidden(KEY, proc)
    assert summary_of(proc).startswith("scanned 1 file, 1 finding,")

    dash = scan(["-"], input=KEY.encode())
    assert dash.returncode == 1
    assert b"-:1:1 aws_access_key block" in dash.stdout
    hidden(KEY, dash)

    js = scan(["--format", "json"], input=KEY.encode())
    rows = json.loads(js.stdout)
    assert rows[0]["path"] == "-" and rows[0]["line"] == 1 and rows[0]["col"] == 1
    hidden(KEY, js)

    (tmp_path / "clean.txt").write_text("ok\n", encoding="utf-8")
    mixed = scan(["clean.txt", "-"], input=KEY.encode(), cwd=tmp_path)
    assert mixed.returncode == 1
    assert summary_of(mixed) == "scanned 2 files, 1 finding, 1 block, 0 coach, 0 allowlisted"
    hidden(KEY, mixed)

    binary = scan([], input=b"\0" + KEY.encode())
    assert binary.returncode == 0
    assert b"aws_access_key" not in binary.stdout
    hidden(KEY, binary)
    assert summary_of(binary) == "scanned 0 files, 0 findings, 0 block, 0 coach, 0 allowlisted"

    empty = scan([], input=b"")
    assert empty.returncode == 0
    assert summary_of(empty) == "scanned 1 file, 0 findings, 0 block, 0 coach, 0 allowlisted"


def test_binary_skip(tmp_path):
    (tmp_path / "notes.txt").write_text(KEY + "\n", encoding="utf-8")
    (tmp_path / "blob.bin").write_bytes(b"\x00\x01" + KEY.encode() + b"\xff")
    (tmp_path / "weird.bin").write_bytes(bytes([0xFF, 0xFE]) + KEY.encode())

    proc = scan(["."], cwd=tmp_path)
    assert proc.returncode == 1
    body = proc.stdout.decode()
    assert "notes.txt:1:1 aws_access_key block" in body
    assert "blob.bin" not in body and "weird.bin" not in body
    assert "blob.bin" not in proc.stderr.decode() and "weird.bin" not in proc.stderr.decode()
    hidden(KEY, proc)
    assert summary_of(proc) == "scanned 1 file, 1 finding, 1 block, 0 coach, 0 allowlisted"

    explicit = scan(["blob.bin"], cwd=tmp_path)
    assert explicit.returncode == 0
    assert b"aws_access_key" not in explicit.stdout
    hidden(KEY, explicit)


def test_pasteguard_wrapper(tmp_path):
    (tmp_path / "a.txt").write_text(KEY + "\n", encoding="utf-8")
    proc = subprocess.run(
        [str(ROOT / "pasteguard"), "scan", "a.txt"],
        cwd=tmp_path, capture_output=True, env=_env(),
    )
    assert proc.returncode == 1, proc.stderr.decode()
    assert b"a.txt:1:1 aws_access_key block" in proc.stdout
    hidden(KEY, proc)

    piped = subprocess.run(
        [str(ROOT / "pasteguard"), "scan"],
        input=KEY.encode(), capture_output=True, env=_env(), cwd=tmp_path,
    )
    assert piped.returncode == 1
    assert piped.stdout.decode().startswith("-:1:1 aws_access_key block")
    hidden(KEY, piped)


def test_coach_rules_are_jwt_and_password_assignment():
    coach = {name for name in RULES if severity(name) == "coach"}
    assert coach == {"jwt", "password_assignment"}
    assert all(severity(name) == "block" for name in RULES if name not in coach)


def test_pre_commit_manifest():
    text = (ROOT / ".pre-commit-hooks.yaml").read_text(encoding="utf-8")
    assert "id: pasteguard-scan" in text
    assert "entry: pasteguard scan" in text
    assert "language: script" in text


def test_scanner_does_not_import_the_model():
    code = (
        "import runpy, sys\n"
        "sys.argv = ['secrets_scan.py', 'scan', '--help']\n"
        "try:\n"
        "    runpy.run_path('secrets_scan.py', run_name='__main__')\n"
        "except SystemExit:\n"
        "    pass\n"
        "bad = {'app', 'embedder', 'index', 'fastembed'}\n"
        "found = bad & set(sys.modules)\n"
        "raise SystemExit('imported ' + ', '.join(sorted(found)) if found else 0)\n"
    )
    proc = subprocess.run([sys.executable, "-c", code], cwd=ROOT / "backend", capture_output=True)
    assert proc.returncode == 0, proc.stderr.decode() + proc.stdout.decode()


def _fingerprint(rule, value):
    return hashlib.sha256(rule.encode() + b"\0" + value.encode()).hexdigest()


def _assert_secret_absent(secret, blob):
    assert secret not in blob
    if len(secret) > 4:
        assert secret[4:] not in blob


def _sarif_results(doc):
    assert doc["version"] == "2.1.0"
    assert "2.1.0" in doc["$schema"]
    assert isinstance(doc["runs"], list) and len(doc["runs"]) == 1
    run = doc["runs"][0]
    assert run["columnKind"] == "unicodeCodePoints"
    driver = run["tool"]["driver"]
    assert driver["name"] == "paste-guard"
    assert driver["version"] == (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    rules = driver["rules"]
    ids = [rule["id"] for rule in rules]
    assert ids == list(RULES)
    assert len(ids) == len(set(ids))
    for rule in rules:
        text = rule["shortDescription"]["text"]
        assert isinstance(text, str) and text.strip()
        assert rule["defaultConfiguration"]["level"] in {"warning", "error", "note", "none"}
    assert set(RULE_DESCRIPTIONS) == set(RULES)
    for result in run["results"]:
        assert result["ruleId"] in ids
        assert result["ruleIndex"] == ids.index(result["ruleId"])
        assert result["level"] in {"warning", "error", "note", "none"}
        assert list(result["message"]) == ["text"]
        assert isinstance(result["message"]["text"], str) and result["message"]["text"]
        loc = result["locations"][0]["physicalLocation"]
        uri = loc["artifactLocation"]["uri"]
        assert isinstance(uri, str) and uri
        assert "://" not in uri and not uri.startswith("/")
        region = loc["region"]
        assert region["startLine"] >= 1 and region["startColumn"] >= 1
        assert "snippet" not in loc
    return run["results"]


def test_sarif_shape_masks_and_exit_codes(tmp_path):
    content = "é " + KEY + "\n"
    (tmp_path / "keys.txt").write_text(content, encoding="utf-8")
    nested = tmp_path / "src"
    nested.mkdir()
    (nested / "my keys.txt").write_text(HF + "\n", encoding="utf-8")
    pw = "hunter2" + "-prod-9x"
    (tmp_path / ".env").write_text("DB_PASSWORD=" + pw + "\n", encoding="utf-8")

    proc = scan(["--format", "sarif", "."], cwd=tmp_path)
    assert proc.returncode == 1
    doc = json.loads(proc.stdout)
    results = _sarif_results(doc)
    by_rule = {row["ruleId"]: row for row in results}
    assert set(by_rule) == {"aws_access_key", "huggingface_token", "password_assignment"}

    aws = by_rule["aws_access_key"]
    assert aws["level"] == "error"
    assert aws["message"]["text"] == f"{KEY[:4]}({len(KEY)})"
    aws_loc = aws["locations"][0]["physicalLocation"]
    assert aws_loc["artifactLocation"]["uri"] == "keys.txt"
    assert aws_loc["region"] == {"startLine": 1, "startColumn": 3}

    hf = by_rule["huggingface_token"]
    assert hf["message"]["text"] == f"{HF[:4]}({len(HF)})"
    assert hf["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] == "src/my%20keys.txt"
    assert hf["locations"][0]["physicalLocation"]["region"] == {"startLine": 1, "startColumn": 1}

    coach = by_rule["password_assignment"]
    assert coach["level"] == "warning"
    assert coach["message"]["text"] == f"{pw[:4]}({len(pw)})"
    assert coach["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] == ".env"

    blob = proc.stdout.decode()
    for secret in (KEY, HF, pw):
        _assert_secret_absent(secret, blob)
        _assert_secret_absent(secret, proc.stderr.decode())
    assert "scanned" not in blob
    assert summary_of(proc, "sarif") == "scanned 3 files, 3 findings, 2 block, 1 coach, 0 allowlisted"

    # Coach alone does not fail, unless --fail-on coach. SARIF does not change that.
    only = scan(["--format", "sarif", ".env"], cwd=tmp_path)
    assert only.returncode == 0
    only_doc = json.loads(only.stdout)
    assert [row["ruleId"] for row in only_doc["runs"][0]["results"]] == ["password_assignment"]
    strict = scan(["--format", "sarif", "--fail-on", "coach", ".env"], cwd=tmp_path)
    assert strict.returncode == 1
    _assert_secret_absent(pw, strict.stdout.decode())

    empty = tmp_path / "empty"
    empty.mkdir()
    none = scan(["--format", "sarif", str(empty)])
    assert none.returncode == 0
    none_doc = json.loads(none.stdout)
    assert none_doc["runs"][0]["results"] == []
    assert len(none_doc["runs"][0]["tool"]["driver"]["rules"]) == len(RULES)
    assert summary_of(none, "sarif") == "scanned 0 files, 0 findings, 0 block, 0 coach, 0 allowlisted"


def test_baseline_round_trip(tmp_path):
    (tmp_path / "a.txt").write_text("prefix " + KEY + "\n", encoding="utf-8")
    base = tmp_path / "baseline.json"

    first = scan(["--write-baseline", str(base), "a.txt"], cwd=tmp_path)
    assert first.returncode == 1
    assert "a.txt:1:8 aws_access_key block" in first.stdout.decode()
    assert "suppressed" not in first.stdout.decode()
    assert "suppressed" not in first.stderr.decode()
    hidden(KEY, first)
    data = json.loads(base.read_text(encoding="utf-8"))
    assert data == {
        "version": 1,
        "findings": [{
            "path": "a.txt",
            "rule": "aws_access_key",
            "fingerprint": _fingerprint("aws_access_key", KEY),
        }],
    }
    stored = base.read_text(encoding="utf-8")
    _assert_secret_absent(KEY, stored)
    assert KEY[:4] not in stored

    second = scan(["--baseline", str(base), "a.txt"], cwd=tmp_path)
    assert second.returncode == 0
    assert "aws_access_key" not in second.stdout.decode()
    assert summary_of(second) == "scanned 1 file, 0 findings, 0 block, 0 coach, 0 allowlisted, 1 suppressed"
    hidden(KEY, second)

    # Same secret, later line: still baselined. A second copy in the same file counts once in the file
    # and twice when both are suppressed.
    (tmp_path / "a.txt").write_text("\n\n" + KEY + "\n" + KEY + "\n", encoding="utf-8")
    moved = scan(["--baseline", str(base), "--format", "json", "a.txt"], cwd=tmp_path)
    assert moved.returncode == 0
    assert json.loads(moved.stdout) == []
    assert summary_of(moved, "json") == "scanned 1 file, 0 findings, 0 block, 0 coach, 0 allowlisted, 2 suppressed"
    _assert_secret_absent(KEY, moved.stdout.decode())
    _assert_secret_absent(KEY, moved.stderr.decode())

    other = "AKIA" + "FFFFFFFFFFFFFFFF"
    (tmp_path / "a.txt").write_text(KEY + "\n" + other + "\n", encoding="utf-8")
    (tmp_path / "b.txt").write_text(KEY + "\n", encoding="utf-8")
    fresh = scan(["--baseline", str(base), "a.txt", "b.txt"], cwd=tmp_path)
    assert fresh.returncode == 1
    body = fresh.stdout.decode()
    assert "a.txt:2:1 aws_access_key block" in body
    assert "b.txt:1:1 aws_access_key block" in body
    assert body.count("aws_access_key") == 2
    assert summary_of(fresh) == "scanned 2 files, 2 findings, 2 block, 0 coach, 0 allowlisted, 1 suppressed"
    hidden(KEY, fresh)
    hidden(other, fresh)

    # Rewriting the baseline records every current finding, then the report still uses the old set.
    both = tmp_path / "both.json"
    both.write_text(base.read_text(encoding="utf-8"), encoding="utf-8")
    rewrite = scan(
        ["--baseline", str(both), "--write-baseline", str(both), "--format", "json", "a.txt"],
        cwd=tmp_path,
    )
    assert rewrite.returncode == 1
    rows = json.loads(rewrite.stdout)
    assert [row["line"] for row in rows] == [2]
    assert "fingerprint" not in rows[0]
    assert summary_of(rewrite, "json").endswith(", 1 suppressed")
    rewritten = json.loads(both.read_text(encoding="utf-8"))
    assert {(item["path"], item["rule"], item["fingerprint"]) for item in rewritten["findings"]} == {
        ("a.txt", "aws_access_key", _fingerprint("aws_access_key", KEY)),
        ("a.txt", "aws_access_key", _fingerprint("aws_access_key", other)),
    }
    _assert_secret_absent(KEY, both.read_text(encoding="utf-8"))
    _assert_secret_absent(other, both.read_text(encoding="utf-8"))

    # An empty baseline suppresses nothing and still reports the count.
    empty = tmp_path / "empty.json"
    (tmp_path / "clean.txt").write_text("hello\n", encoding="utf-8")
    made = scan(["--write-baseline", str(empty), "clean.txt"], cwd=tmp_path)
    assert made.returncode == 0
    assert json.loads(empty.read_text(encoding="utf-8")) == {"version": 1, "findings": []}
    counted = scan(["--baseline", str(empty), "a.txt"], cwd=tmp_path)
    assert counted.returncode == 1
    assert summary_of(counted).endswith(", 0 suppressed")


def test_baseline_hashes_secret_value(tmp_path):
    pw = "hunter2" + "-prod-9x"
    db_pw = "s3cret" + "-token"
    url = "postgres://user:" + db_pw + "@db.example.com/app"
    (tmp_path / ".env").write_text('DB_PASSWORD="' + pw + '"\n' + url + "\n", encoding="utf-8")
    base = tmp_path / "base.json"
    proc = scan(["--write-baseline", str(base), "--format", "sarif", ".env"], cwd=tmp_path)
    assert proc.returncode == 1
    data = json.loads(base.read_text(encoding="utf-8"))
    fps = {item["rule"]: item["fingerprint"] for item in data["findings"]}
    assert fps["password_assignment"] == _fingerprint("password_assignment", pw)
    assert fps["db_url_password"] == _fingerprint("db_url_password", db_pw)
    blob = base.read_text(encoding="utf-8")
    for secret in (pw, db_pw, url, "DB_PASSWORD"):
        assert secret not in blob
    doc = json.loads(proc.stdout)
    messages = [row["message"]["text"] for row in doc["runs"][0]["results"]]
    assert messages == [f"{pw[:4]}({len(pw)})", f"{db_pw[:4]}({len(db_pw)})"]
    for secret in (pw, db_pw, url):
        _assert_secret_absent(secret, proc.stdout.decode())
        _assert_secret_absent(secret, blob)


def test_baseline_and_allowlist(tmp_path):
    stripe = "sk_live_" + ("B" * 24)
    (tmp_path / "both.txt").write_text(KEY + "\n" + stripe + "\n", encoding="utf-8")
    base = tmp_path / "base.json"
    wrote = scan(["--write-baseline", str(base), "both.txt"], cwd=tmp_path)
    assert wrote.returncode == 1
    stored = json.loads(base.read_text(encoding="utf-8"))
    assert {item["rule"] for item in stored["findings"]} == {"aws_access_key", "stripe_key"}
    blob = base.read_text(encoding="utf-8")
    _assert_secret_absent(KEY, blob)
    _assert_secret_absent(stripe, blob)

    listed = tmp_path / "allow.txt"
    listed.write_text("value:" + KEY + "\n", encoding="utf-8")
    env = {"PG_SECRETS_ALLOWLIST": str(listed)}

    # Allowlist wins over the baseline: KEY is allowlisted, not suppressed. Stripe is suppressed.
    quiet = scan(["--baseline", str(base), "both.txt"], cwd=tmp_path, env=env)
    assert quiet.returncode == 0
    assert "aws_access_key" not in quiet.stdout.decode()
    assert "stripe_key" not in quiet.stdout.decode()
    assert summary_of(quiet) == "scanned 1 file, 0 findings, 0 block, 0 coach, 1 allowlisted, 1 suppressed"
    hidden(KEY, quiet)
    hidden(stripe, quiet)

    js = scan(["--baseline", str(base), "--format", "json", "both.txt"], cwd=tmp_path, env=env)
    assert js.returncode == 0
    assert json.loads(js.stdout) == []
    assert summary_of(js, "json") == summary_of(quiet)
    hidden(KEY, js)
    hidden(stripe, js)

    # A new secret is still reported and fails the run. The allowlisted key stays out of a new baseline.
    (tmp_path / "both.txt").write_text(KEY + "\n" + stripe + "\n" + HF + "\n", encoding="utf-8")
    new_base = tmp_path / "new.json"
    reported = scan(
        ["--baseline", str(base), "--write-baseline", str(new_base), "--format", "sarif", "both.txt"],
        cwd=tmp_path, env=env,
    )
    assert reported.returncode == 1
    doc = json.loads(reported.stdout)
    results = doc["runs"][0]["results"]
    assert [row["ruleId"] for row in results] == ["huggingface_token"]
    assert results[0]["message"]["text"] == f"{HF[:4]}({len(HF)})"
    assert results[0]["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] == "both.txt"
    assert summary_of(reported, "sarif") == "scanned 1 file, 1 finding, 1 block, 0 coach, 1 allowlisted, 1 suppressed"
    for secret in (KEY, stripe, HF):
        _assert_secret_absent(secret, reported.stdout.decode())
        _assert_secret_absent(secret, reported.stderr.decode())
    fresh = json.loads(new_base.read_text(encoding="utf-8"))
    assert {item["rule"] for item in fresh["findings"]} == {"stripe_key", "huggingface_token"}
    fresh_blob = new_base.read_text(encoding="utf-8")
    for secret in (KEY, stripe, HF):
        _assert_secret_absent(secret, fresh_blob)

    # Without the allowlist, KEY is new relative to a baseline that never recorded it.
    only_stripe = scan(["--baseline", str(new_base), "both.txt"], cwd=tmp_path)
    assert only_stripe.returncode == 1
    body = only_stripe.stdout.decode()
    assert "aws_access_key" in body
    assert "stripe_key" not in body
    assert "huggingface_token" not in body
    assert summary_of(only_stripe) == "scanned 1 file, 1 finding, 1 block, 0 coach, 0 allowlisted, 2 suppressed"
    hidden(KEY, only_stripe)
    hidden(stripe, only_stripe)
    hidden(HF, only_stripe)


def test_baseline_usage_errors(tmp_path):
    (tmp_path / "a.txt").write_text(KEY + "\n", encoding="utf-8")
    missing = scan(["--baseline", str(tmp_path / "nope.json"), "a.txt"], cwd=tmp_path)
    assert missing.returncode == 2
    assert b"baseline not found" in missing.stderr
    hidden(KEY, missing)

    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    broken = scan(["--baseline", str(bad), "a.txt"], cwd=tmp_path)
    assert broken.returncode == 2
    assert b"not valid JSON" in broken.stderr
    hidden(KEY, broken)

    wrong = tmp_path / "wrong.json"
    wrong.write_text('{"version": 2, "findings": []}\n', encoding="utf-8")
    unrecognized = scan(["--baseline", str(wrong), "a.txt"], cwd=tmp_path)
    assert unrecognized.returncode == 2
    assert b"unrecognized baseline" in unrecognized.stderr

    nested = tmp_path / "missing-dir"
    refused = scan(["--write-baseline", str(nested / "base.json"), "a.txt"], cwd=tmp_path)
    assert refused.returncode == 2
    assert b"baseline directory not found" in refused.stderr
    hidden(KEY, refused)
    assert not nested.exists()

    assert scan(["--baseline"]).returncode == 2
    assert scan(["--write-baseline"]).returncode == 2
    help_proc = scan(["--help"])
    text = help_proc.stdout.decode()
    assert "sarif" in text
    assert "--baseline" in text
    assert "--write-baseline" in text


def test_fingerprint_still_works():
    proc = subprocess.run(
        [sys.executable, str(ROOT / "backend" / "secrets_scan.py")],
        input=b"abc\n", capture_output=True, check=True,
    )
    assert proc.stdout.decode().strip() == hashlib.sha256(b"abc").hexdigest()
    usage = subprocess.run(
        [sys.executable, str(ROOT / "backend" / "secrets_scan.py"), "nope"],
        input=b"x", capture_output=True,
    )
    assert usage.returncode == 2
