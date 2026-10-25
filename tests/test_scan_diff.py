"""pasteguard scan --staged and --diff-base. Temporary git repos, no real keys."""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from secrets_scan import _on_added_lines, _parse_added_lines  # noqa: E402

SCAN = [sys.executable, str(ROOT / "backend" / "secrets_scan.py"), "scan"]

KEY = "AKIA" + "0123456789ABCDEF"
OLD = "AKIA" + ("F" * 16)
HF = "hf_" + ("A" * 34)
STRIPE = "sk_live_" + ("B" * 24)


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


def scan(args, *, env=None, cwd=None):
    return subprocess.run(
        SCAN + list(args),
        capture_output=True,
        cwd=cwd,
        env=_env(**(env or {})),
    )


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


def _fingerprint(rule, value):
    return hashlib.sha256(rule.encode() + b"\0" + value.encode()).hexdigest()


def test_parse_added_lines_and_spans():
    added = _parse_added_lines(
        b"diff --git a/a b/a\n--- a/a\n+++ b/a\n@@ -1,0 +2 @@\n+line\n"
    )
    assert added == {2}
    assert _parse_added_lines(b"Binary files a/a.bin and b/a.bin differ\n") is None
    # A rewritten last line with no newline, then one new line. Both count.
    nonew = (
        b"@@ -1 +1,2 @@\n"
        b"-hello\n"
        b"\\ No newline at end of file\n"
        b"+hello\n"
        b"+more\n"
        b"\\ No newline at end of file\n"
    )
    assert _parse_added_lines(nonew) == {1, 2}
    # The new line's text is "++keep". In the diff that is one '+' marker plus "++keep".
    plus = b"@@ -3,0 +4,2 @@\n+++keep\n+next\n"
    assert _parse_added_lines(plus) == {4, 5}

    text = "aaa\nbbb\nccc\n"
    start = text.index("bbb")
    end = start + 3
    assert _on_added_lines(text, {"start": start, "end": end}, {2})
    assert not _on_added_lines(text, {"start": start, "end": end}, {1, 3})
    # Touches line 1 (unchanged) and line 2 (added).
    assert not _on_added_lines(text, {"start": 0, "end": end}, {2})
    assert _on_added_lines(text, {"start": 0, "end": end}, {1, 2})


def test_staged_addition_found(tmp_path):
    repo = init_repo(tmp_path / "repo")
    (repo / "app.txt").write_text("hello\n", encoding="utf-8")
    commit_all(repo, "init")
    (repo / "app.txt").write_text("hello\n  " + KEY + "\n", encoding="utf-8")
    git(repo, "add", "app.txt")

    proc = scan(["--staged"], cwd=repo)
    assert proc.returncode == 1
    assert f"app.txt:2:3 aws_access_key block {KEY[:4]}({len(KEY)})" in proc.stdout.decode()
    assert summary_of(proc) == "scanned 1 file, 1 finding, 1 block, 0 coach, 0 allowlisted, 0 inline"
    hidden(KEY, proc)

    js = scan(["--staged", "--format", "json"], cwd=repo)
    assert js.returncode == 1
    rows = json.loads(js.stdout)
    assert rows == [{
        "path": "app.txt", "line": 2, "col": 3, "rule": "aws_access_key", "severity": "block",
        "mask": f"{KEY[:4]}({len(KEY)})", "length": len(KEY),
    }]
    hidden(KEY, js)
    assert summary_of(js, "json") == summary_of(proc)


def test_staged_ignores_unstaged_and_reads_the_index(tmp_path):
    repo = init_repo(tmp_path / "repo")
    (repo / "app.txt").write_text("hello\n", encoding="utf-8")
    commit_all(repo, "init")

    # Index has the secret. The working tree no longer does.
    (repo / "app.txt").write_text("hello\n" + KEY + "\n", encoding="utf-8")
    git(repo, "add", "app.txt")
    (repo / "app.txt").write_text("hello\nnope\n", encoding="utf-8")
    (repo / "later.txt").write_text(HF + "\n", encoding="utf-8")

    proc = scan(["--staged"], cwd=repo)
    assert proc.returncode == 1
    body = proc.stdout.decode()
    assert f"app.txt:2:1 aws_access_key block {KEY[:4]}({len(KEY)})" in body
    assert "later.txt" not in body
    assert "huggingface" not in body
    hidden(KEY, proc)
    hidden(HF, proc)

    # Nothing staged: the worktree secret is invisible.
    git(repo, "reset", "-q", "HEAD")
    (repo / "app.txt").write_text("hello\n" + HF + "\n", encoding="utf-8")
    quiet = scan(["--staged"], cwd=repo)
    assert quiet.returncode == 0
    assert "huggingface" not in quiet.stdout.decode()
    assert summary_of(quiet) == "scanned 0 files, 0 findings, 0 block, 0 coach, 0 allowlisted, 0 inline"
    hidden(HF, quiet)


def test_unchanged_secret_ignored(tmp_path):
    repo = init_repo(tmp_path / "repo")
    (repo / "app.txt").write_text(KEY + "\nkeep\n", encoding="utf-8")
    commit_all(repo, "init")
    (repo / "app.txt").write_text(KEY + "\nkeep\nnote\n", encoding="utf-8")
    git(repo, "add", "app.txt")

    quiet = scan(["--staged"], cwd=repo)
    assert quiet.returncode == 0
    assert "aws_access_key" not in quiet.stdout.decode()
    assert summary_of(quiet) == "scanned 1 file, 0 findings, 0 block, 0 coach, 0 allowlisted, 0 inline"
    hidden(KEY, quiet)

    (repo / "app.txt").write_text(KEY + "\nkeep\n" + HF + "\n", encoding="utf-8")
    git(repo, "add", "app.txt")
    proc = scan(["--staged"], cwd=repo)
    assert proc.returncode == 1
    body = proc.stdout.decode()
    assert f"app.txt:3:1 huggingface_token block {HF[:4]}({len(HF)})" in body
    assert "aws_access_key" not in body
    assert summary_of(proc) == "scanned 1 file, 1 finding, 1 block, 0 coach, 0 allowlisted, 0 inline"
    hidden(KEY, proc)
    hidden(HF, proc)


def test_changed_line_reports_the_secret_on_it(tmp_path):
    repo = init_repo(tmp_path / "repo")
    (repo / "app.txt").write_text("prefix " + KEY + "\n", encoding="utf-8")
    commit_all(repo, "init")
    (repo / "app.txt").write_text("pre " + KEY + "\n", encoding="utf-8")
    git(repo, "add", "app.txt")
    proc = scan(["--staged"], cwd=repo)
    assert proc.returncode == 1
    assert "app.txt:1:5 aws_access_key block" in proc.stdout.decode()
    hidden(KEY, proc)


def test_diff_base_on_a_branch(tmp_path):
    repo = init_repo(tmp_path / "repo")
    (repo / "app.txt").write_text("base\n" + KEY + "\n", encoding="utf-8")
    commit_all(repo, "init")
    git(repo, "checkout", "-b", "feature")
    (repo / "app.txt").write_text("base\n" + KEY + "\n" + HF + "\n", encoding="utf-8")
    (repo / "new.txt").write_text(STRIPE + "\n", encoding="utf-8")
    commit_all(repo, "add")
    # Uncommitted. --diff-base compares commits, so this file stays out.
    (repo / "extra.txt").write_text(KEY + "\n", encoding="utf-8")

    proc = scan(["--diff-base", "main", "--format", "sarif"], cwd=repo)
    assert proc.returncode == 1
    doc = json.loads(proc.stdout)
    results = doc["runs"][0]["results"]
    by_rule = {row["ruleId"]: row for row in results}
    assert set(by_rule) == {"huggingface_token", "stripe_key"}
    hf_loc = by_rule["huggingface_token"]["locations"][0]["physicalLocation"]
    assert hf_loc["artifactLocation"]["uri"] == "app.txt"
    assert hf_loc["region"] == {"startLine": 3, "startColumn": 1}
    assert by_rule["huggingface_token"]["message"]["text"] == f"{HF[:4]}({len(HF)})"
    stripe_loc = by_rule["stripe_key"]["locations"][0]["physicalLocation"]
    assert stripe_loc["artifactLocation"]["uri"] == "new.txt"
    assert stripe_loc["region"]["startLine"] == 1
    blob = proc.stdout.decode() + proc.stderr.decode()
    assert "extra.txt" not in blob
    for secret in (KEY, HF, STRIPE):
        hidden(secret, proc)
    assert summary_of(proc, "sarif") == "scanned 2 files, 2 findings, 2 block, 0 coach, 0 allowlisted, 0 inline"


def test_rename(tmp_path):
    repo = init_repo(tmp_path / "repo")
    original = "one\n" + KEY + "\ntwo\nthree\nfour\nfive\n"
    (repo / "old.txt").write_text(original, encoding="utf-8")
    commit_all(repo, "init")
    git(repo, "mv", "old.txt", "new.txt")
    pure = scan(["--staged"], cwd=repo)
    assert pure.returncode == 0
    assert "aws_access_key" not in pure.stdout.decode()
    assert "new.txt" not in pure.stdout.decode()
    hidden(KEY, pure)
    assert summary_of(pure) == "scanned 0 files, 0 findings, 0 block, 0 coach, 0 allowlisted, 0 inline"

    (repo / "new.txt").write_text(original + HF + "\n", encoding="utf-8")
    git(repo, "add", "new.txt")
    status = git(repo, "diff", "--cached", "--find-renames", "--name-status").stdout.decode()
    assert status.startswith("R"), status
    proc = scan(["--staged"], cwd=repo)
    assert proc.returncode == 1
    body = proc.stdout.decode()
    assert f"new.txt:7:1 huggingface_token block {HF[:4]}({len(HF)})" in body
    assert "old.txt" not in body
    assert "aws_access_key" not in body
    hidden(KEY, proc)
    hidden(HF, proc)


def test_deleted_file(tmp_path):
    repo = init_repo(tmp_path / "repo")
    (repo / "gone.txt").write_text(KEY + "\n", encoding="utf-8")
    commit_all(repo, "init")
    git(repo, "rm", "gone.txt")
    proc = scan(["--staged"], cwd=repo)
    assert proc.returncode == 0
    assert "aws_access_key" not in proc.stdout.decode()
    assert "gone.txt" not in proc.stdout.decode()
    hidden(KEY, proc)
    assert summary_of(proc) == "scanned 0 files, 0 findings, 0 block, 0 coach, 0 allowlisted, 0 inline"


def test_binary_file(tmp_path):
    repo = init_repo(tmp_path / "repo")
    (repo / "notes.txt").write_text("clean\n", encoding="utf-8")
    commit_all(repo, "init")
    (repo / "blob.bin").write_bytes(b"\x00\x01" + KEY.encode() + b"\xff")
    (repo / "notes.txt").write_text("clean\n" + HF + "\n", encoding="utf-8")
    git(repo, "add", "blob.bin", "notes.txt")
    proc = scan(["--staged"], cwd=repo)
    assert proc.returncode == 1
    body = proc.stdout.decode()
    assert "notes.txt:2:1 huggingface_token block" in body
    assert "blob.bin" not in body
    assert "aws_access_key" not in body
    hidden(KEY, proc)
    hidden(HF, proc)
    assert summary_of(proc) == "scanned 1 file, 1 finding, 1 block, 0 coach, 0 allowlisted, 0 inline"


def test_bad_ref(tmp_path):
    repo = init_repo(tmp_path / "repo")
    empty = scan(["--diff-base", "main"], cwd=repo)
    assert empty.returncode == 2
    assert b"no commits yet" in empty.stderr

    (repo / "app.txt").write_text("ok\n", encoding="utf-8")
    commit_all(repo, "init")
    bad = scan(["--diff-base", "no-such-ref"], cwd=repo)
    assert bad.returncode == 2
    assert b"ref not found: no-such-ref" in bad.stderr
    assert b"aws_access_key" not in bad.stdout


def test_not_a_git_repo(tmp_path):
    staged = scan(["--staged"], cwd=tmp_path)
    assert staged.returncode == 2
    assert b"not a git repository" in staged.stderr

    base = scan(["--diff-base", "main"], cwd=tmp_path)
    assert base.returncode == 2
    assert b"not a git repository" in base.stderr


def test_diff_flags_reject_paths(tmp_path):
    repo = init_repo(tmp_path / "repo")
    (repo / "app.txt").write_text("ok\n", encoding="utf-8")
    both = scan(["--staged", "--diff-base", "main"], cwd=repo)
    assert both.returncode == 2
    assert b"use either --staged or --diff-base" in both.stderr

    staged = scan(["--staged", "app.txt"], cwd=repo)
    assert staged.returncode == 2
    assert b"--staged does not take path arguments" in staged.stderr

    base = scan(["--diff-base", "main", "app.txt"], cwd=repo)
    assert base.returncode == 2
    assert b"--diff-base does not take path arguments" in base.stderr

    help_proc = scan(["--help"])
    text = help_proc.stdout.decode()
    assert "--staged" in text
    assert "--diff-base" in text


def test_exclude_and_vendor_on_staged(tmp_path):
    repo = init_repo(tmp_path / "repo")
    (repo / "keep.txt").write_text(KEY + "\n", encoding="utf-8")
    (repo / "skip.txt").write_text(HF + "\n", encoding="utf-8")
    vendor = repo / "node_modules" / "pkg"
    vendor.mkdir(parents=True)
    (vendor / "index.js").write_text(STRIPE + "\n", encoding="utf-8")
    git(repo, "add", "-A")
    proc = scan(["--staged", "--exclude", "skip.txt"], cwd=repo)
    assert proc.returncode == 1
    body = proc.stdout.decode()
    assert "keep.txt:1:1 aws_access_key block" in body
    assert "skip.txt" not in body
    assert "node_modules" not in body
    assert "stripe_key" not in body
    assert "huggingface" not in body
    for secret in (KEY, HF, STRIPE):
        hidden(secret, proc)
    assert summary_of(proc) == "scanned 1 file, 1 finding, 1 block, 0 coach, 0 allowlisted, 0 inline"


def test_fail_on_applies_to_added_lines(tmp_path):
    repo = init_repo(tmp_path / "repo")
    pw = "hunter2" + "-prod-9x"
    (repo / ".env").write_text("x=1\n", encoding="utf-8")
    commit_all(repo, "init")
    (repo / ".env").write_text("x=1\nDB_PASSWORD=" + pw + "\n", encoding="utf-8")
    git(repo, "add", ".env")
    base = scan(["--staged"], cwd=repo)
    assert base.returncode == 0
    assert ".env:2:1 password_assignment coach" in base.stdout.decode()
    hidden(pw, base)
    strict = scan(["--staged", "--fail-on", "coach"], cwd=repo)
    assert strict.returncode == 1
    hidden(pw, strict)


def test_staged_before_first_commit(tmp_path):
    repo = init_repo(tmp_path / "repo")
    (repo / "app.txt").write_text(KEY + "\n", encoding="utf-8")
    git(repo, "add", "app.txt")
    proc = scan(["--staged"], cwd=repo)
    assert proc.returncode == 1
    assert "app.txt:1:1 aws_access_key block" in proc.stdout.decode()
    hidden(KEY, proc)


def test_baseline_and_allowlist_on_added_lines(tmp_path):
    repo = init_repo(tmp_path / "repo")
    (repo / "app.txt").write_text(OLD + "\nkeep\n", encoding="utf-8")
    commit_all(repo, "init")
    git(repo, "checkout", "-b", "feature")
    (repo / "app.txt").write_text(
        OLD + "\nkeep\n" + KEY + "\n" + STRIPE + "\n" + HF + "\n",
        encoding="utf-8",
    )
    commit_all(repo, "add")

    base = repo / "baseline.json"
    base.write_text(json.dumps({
        "version": 1,
        "findings": [
            {"path": "app.txt", "rule": "aws_access_key", "fingerprint": _fingerprint("aws_access_key", OLD)},
            {"path": "app.txt", "rule": "stripe_key", "fingerprint": _fingerprint("stripe_key", STRIPE)},
        ],
    }), encoding="utf-8")
    listed = repo / "allow.txt"
    listed.write_text("value:" + KEY + "\n", encoding="utf-8")
    env = {"PG_SECRETS_ALLOWLIST": str(listed)}
    fresh = repo / "fresh.json"

    proc = scan(
        ["--diff-base", "main", "--baseline", str(base), "--write-baseline", str(fresh)],
        cwd=repo, env=env,
    )
    assert proc.returncode == 1
    body = proc.stdout.decode()
    assert f"app.txt:5:1 huggingface_token block {HF[:4]}({len(HF)})" in body
    assert "aws_access_key" not in body
    assert "stripe_key" not in body
    # OLD sits on an unchanged line, so it is not a suppressed finding.
    # KEY is allowlisted. STRIPE is on an added line and is in the baseline.
    assert summary_of(proc) == "scanned 1 file, 1 finding, 1 block, 0 coach, 1 allowlisted, 0 inline, 1 suppressed"
    for secret in (OLD, KEY, STRIPE, HF):
        hidden(secret, proc)

    stored = json.loads(fresh.read_text(encoding="utf-8"))
    assert {item["rule"] for item in stored["findings"]} == {"stripe_key", "huggingface_token"}
    blob = fresh.read_text(encoding="utf-8")
    for secret in (OLD, KEY, STRIPE, HF):
        assert secret not in blob
        if len(secret) > 4:
            assert secret[4:] not in blob


def test_pre_commit_staged_hook():
    text = (ROOT / ".pre-commit-hooks.yaml").read_text(encoding="utf-8")
    assert "id: pasteguard-scan-staged" in text
    assert "entry: pasteguard scan --staged" in text
    assert "pass_filenames: false" in text
    assert "id: pasteguard-scan\n" in text
