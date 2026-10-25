"""pasteguard:ignore comments. No model, no index, no real keys."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from secrets_scan import _apply_inline, _parse_markers  # noqa: E402

SCAN = [sys.executable, str(ROOT / "backend" / "secrets_scan.py"), "scan"]

KEY = "AKIA" + "0123456789ABCDEF"
HF = "hf_" + ("A" * 34)
BEGIN = "-----BEGIN RSA PRIVATE KEY-----"
END = "-----END RSA PRIVATE KEY-----"

# The marker text is what matters. The characters around it are just the comment.
COMMENT_STYLES = [
    "# pasteguard:ignore",
    "// pasteguard:ignore",
    "-- pasteguard:ignore",
    "/* pasteguard:ignore */",
    "<!-- pasteguard:ignore -->",
    "; pasteguard:ignore",
]
NEXT_LINE_STYLES = [
    "# pasteguard:ignore-next-line",
    "// pasteguard:ignore-next-line",
    "-- pasteguard:ignore-next-line",
    "/* pasteguard:ignore-next-line */",
    "<!-- pasteguard:ignore-next-line -->",
    "; pasteguard:ignore-next-line",
]


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


@pytest.mark.parametrize("comment", COMMENT_STYLES)
def test_same_line_comment_styles(tmp_path, comment):
    (tmp_path / "f.txt").write_text(KEY + "  " + comment + "\n", encoding="utf-8")
    proc = scan(["f.txt"], cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr.decode()
    assert "aws_access_key" not in proc.stdout.decode()
    assert summary_of(proc) == "scanned 1 file, 0 findings, 0 block, 0 coach, 0 allowlisted, 1 inline"
    hidden(KEY, proc)


@pytest.mark.parametrize("comment", NEXT_LINE_STYLES)
def test_ignore_next_line_comment_styles(tmp_path, comment):
    (tmp_path / "f.txt").write_text(comment + "\n" + KEY + "\n", encoding="utf-8")
    proc = scan(["f.txt"], cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr.decode()
    assert "aws_access_key" not in proc.stdout.decode()
    assert summary_of(proc) == "scanned 1 file, 0 findings, 0 block, 0 coach, 0 allowlisted, 1 inline"
    hidden(KEY, proc)


def test_rule_scope_leaves_other_detectors(tmp_path):
    line = KEY + " " + HF + "  # pasteguard:ignore=aws_access_key\n"
    (tmp_path / "f.txt").write_text(line, encoding="utf-8")
    proc = scan(["f.txt"], cwd=tmp_path)
    assert proc.returncode == 1
    body = proc.stdout.decode()
    assert "aws_access_key" not in body
    assert "huggingface_token" in body
    assert summary_of(proc) == "scanned 1 file, 1 finding, 1 block, 0 coach, 0 allowlisted, 1 inline"
    hidden(KEY, proc)
    hidden(HF, proc)

    both = KEY + " " + HF + "  # pasteguard:ignore=aws_access_key, huggingface_token\n"
    (tmp_path / "f.txt").write_text(both, encoding="utf-8")
    quiet = scan(["f.txt"], cwd=tmp_path)
    assert quiet.returncode == 0
    assert "aws_access_key" not in quiet.stdout.decode()
    assert "huggingface" not in quiet.stdout.decode()
    assert summary_of(quiet) == "scanned 1 file, 0 findings, 0 block, 0 coach, 0 allowlisted, 2 inline"
    hidden(KEY, quiet)
    hidden(HF, quiet)

    # An HTML closer sits against the rule name. The hyphens are not part of the id.
    html = KEY + " <!-- pasteguard:ignore=aws_access_key-->\n"
    (tmp_path / "f.txt").write_text(html, encoding="utf-8")
    closed = scan(["f.txt"], cwd=tmp_path)
    assert closed.returncode == 0
    assert summary_of(closed).endswith("1 inline")
    hidden(KEY, closed)


def test_ignore_next_line_is_not_a_same_line_ignore(tmp_path):
    text = (
        KEY + " # pasteguard:ignore-next-line\n"
        + HF + "\n"
    )
    (tmp_path / "f.txt").write_text(text, encoding="utf-8")
    proc = scan(["f.txt"], cwd=tmp_path)
    assert proc.returncode == 1
    body = proc.stdout.decode()
    assert "aws_access_key" in body
    assert "huggingface" not in body
    assert summary_of(proc) == "scanned 1 file, 1 finding, 1 block, 0 coach, 0 allowlisted, 1 inline"
    hidden(KEY, proc)
    hidden(HF, proc)

    scoped = "# pasteguard:ignore-next-line=huggingface_token\n" + KEY + " " + HF + "\n"
    (tmp_path / "f.txt").write_text(scoped, encoding="utf-8")
    scoped_proc = scan(["f.txt"], cwd=tmp_path)
    assert scoped_proc.returncode == 1
    body = scoped_proc.stdout.decode()
    assert "aws_access_key" in body
    assert "huggingface" not in body
    hidden(KEY, scoped_proc)
    hidden(HF, scoped_proc)


def test_nearby_words_are_not_markers(tmp_path):
    (tmp_path / "f.txt").write_text(KEY + " # pasteguard:ignored\n", encoding="utf-8")
    proc = scan(["f.txt"], cwd=tmp_path)
    assert proc.returncode == 1
    assert "aws_access_key" in proc.stdout.decode()
    assert b"unknown rule" not in proc.stderr
    hidden(KEY, proc)

    (tmp_path / "f.txt").write_text("# pasteguard:ignore-next-lineage\n" + KEY + "\n", encoding="utf-8")
    nxt = scan(["f.txt"], cwd=tmp_path)
    assert nxt.returncode == 1
    assert "aws_access_key" in nxt.stdout.decode()
    hidden(KEY, nxt)


def test_multiline_span_uses_the_first_line():
    text = "AAAA # pasteguard:ignore\nBBBB\nCCCC\n"
    finding = {"type": "private_key", "start": 0, "end": len(text) - 1}
    kept, suppressed, unused = _apply_inline(text, [finding], _parse_markers(text), None)
    assert kept == []
    assert len(suppressed) == 1
    assert unused == []

    later = "AAAA\nBBBB # pasteguard:ignore\nCCCC\n"
    finding = {"type": "private_key", "start": 0, "end": len(later) - 1}
    kept, suppressed, unused = _apply_inline(later, [finding], _parse_markers(later), None)
    assert len(kept) == 1 and suppressed == []
    assert len(unused) == 1 and unused[0].line == 2

    nxt = "# pasteguard:ignore-next-line\nAAAA\nBBBB\n"
    start = nxt.index("AAAA")
    finding = {"type": "private_key", "start": start, "end": len(nxt) - 1}
    # The marker line is not in the diff. The span still starts on the next line.
    kept, suppressed, unused = _apply_inline(nxt, [finding], _parse_markers(nxt), {2, 3})
    assert kept == []
    assert len(suppressed) == 1
    assert unused == []


def test_private_key_block(tmp_path):
    marked = BEGIN + "  # pasteguard:ignore\nMIIEow\n" + END + "\n"
    (tmp_path / "k.pem").write_text(marked, encoding="utf-8")
    proc = scan(["k.pem"], cwd=tmp_path)
    assert proc.returncode == 0
    assert "private_key" not in proc.stdout.decode()
    assert summary_of(proc).endswith("1 inline")

    below = BEGIN + "\nMIIEow  # pasteguard:ignore\n" + END + "\n"
    (tmp_path / "k.pem").write_text(below, encoding="utf-8")
    shown = scan(["k.pem"], cwd=tmp_path)
    assert shown.returncode == 1
    assert "private_key" in shown.stdout.decode()
    assert summary_of(shown).endswith("0 inline")

    above = "# pasteguard:ignore-next-line\n" + BEGIN + "\nMIIEow\n" + END + "\n"
    (tmp_path / "k.pem").write_text(above, encoding="utf-8")
    quiet = scan(["k.pem"], cwd=tmp_path)
    assert quiet.returncode == 0
    assert "private_key" not in quiet.stdout.decode()
    assert summary_of(quiet).endswith("1 inline")


def test_stdin_and_json_omit_the_finding(tmp_path):
    proc = scan([], input=(KEY + " # pasteguard:ignore\n").encode())
    assert proc.returncode == 0
    assert proc.stdout.decode().strip() == summary_of(proc)
    assert "aws_access_key" not in proc.stdout.decode()
    hidden(KEY, proc)

    nxt = scan([], input=("# pasteguard:ignore-next-line\n" + KEY + "\n").encode())
    assert nxt.returncode == 0
    assert summary_of(nxt).endswith("1 inline")
    hidden(KEY, nxt)

    (tmp_path / "f.txt").write_text(KEY + " # pasteguard:ignore\n" + HF + "\n", encoding="utf-8")
    js = scan(["--format", "json", "f.txt"], cwd=tmp_path)
    assert js.returncode == 1
    rows = json.loads(js.stdout)
    assert [row["rule"] for row in rows] == ["huggingface_token"]
    assert "inline" not in js.stdout.decode()
    assert summary_of(js, "json") == "scanned 1 file, 1 finding, 1 block, 0 coach, 0 allowlisted, 1 inline"
    hidden(KEY, js)
    hidden(HF, js)


def test_sarif_keeps_an_in_source_suppression(tmp_path):
    (tmp_path / "f.txt").write_text(
        KEY + " # pasteguard:ignore\n" + HF + "\n",
        encoding="utf-8",
    )
    proc = scan(["--format", "sarif", "f.txt"], cwd=tmp_path)
    assert proc.returncode == 1
    doc = json.loads(proc.stdout)
    results = doc["runs"][0]["results"]
    by_rule = {row["ruleId"]: row for row in results}
    assert set(by_rule) == {"aws_access_key", "huggingface_token"}
    assert by_rule["aws_access_key"]["suppressions"] == [{"kind": "inSource", "status": "accepted"}]
    assert by_rule["aws_access_key"]["level"] == "error"
    assert "suppressions" not in by_rule["huggingface_token"]
    assert by_rule["aws_access_key"]["locations"][0]["physicalLocation"]["region"]["startLine"] == 1
    assert summary_of(proc, "sarif").endswith("1 inline")
    hidden(KEY, proc)
    hidden(HF, proc)

    (tmp_path / "f.txt").write_text(KEY + " # pasteguard:ignore\n", encoding="utf-8")
    only = scan(["--format", "sarif", "f.txt"], cwd=tmp_path)
    assert only.returncode == 0
    rows = json.loads(only.stdout)["runs"][0]["results"]
    assert len(rows) == 1
    assert rows[0]["suppressions"][0]["kind"] == "inSource"
    assert summary_of(only, "sarif") == "scanned 1 file, 0 findings, 0 block, 0 coach, 0 allowlisted, 1 inline"
    hidden(KEY, only)


def test_no_inline_ignore_reports_the_finding(tmp_path):
    (tmp_path / "f.txt").write_text(KEY + " # pasteguard:ignore\n", encoding="utf-8")
    proc = scan(["--no-inline-ignore", "f.txt"], cwd=tmp_path)
    assert proc.returncode == 1
    assert "aws_access_key" in proc.stdout.decode()
    assert "inline" not in summary_of(proc)
    hidden(KEY, proc)

    sarif = scan(["--no-inline-ignore", "--format", "sarif", "f.txt"], cwd=tmp_path)
    assert sarif.returncode == 1
    row = json.loads(sarif.stdout)["runs"][0]["results"][0]
    assert row["ruleId"] == "aws_access_key"
    assert "suppressions" not in row
    hidden(KEY, sarif)

    # Markers are off, so unused reporting does not invent hits from them.
    both = scan(["--no-inline-ignore", "--report-unused-ignores", "f.txt"], cwd=tmp_path)
    assert both.returncode == 1
    assert "unused" not in both.stdout.decode()
    assert "aws_access_key" in both.stdout.decode()
    hidden(KEY, both)


def test_unknown_rule_warns_and_does_not_crash(tmp_path):
    (tmp_path / "f.txt").write_text(KEY + " # pasteguard:ignore=no_such_rule\n", encoding="utf-8")
    proc = scan(["f.txt"], cwd=tmp_path)
    assert proc.returncode == 1
    assert b"Traceback" not in proc.stderr
    assert "unknown rule 'no_such_rule' in pasteguard:ignore" in proc.stderr.decode()
    assert "f.txt:1:" in proc.stderr.decode()
    assert "aws_access_key" in proc.stdout.decode()
    hidden(KEY, proc)

    (tmp_path / "f.txt").write_text(
        KEY + " # pasteguard:ignore=aws_access_key,no_such_rule\n",
        encoding="utf-8",
    )
    mixed = scan(["f.txt"], cwd=tmp_path)
    assert mixed.returncode == 0
    assert "unknown rule 'no_such_rule'" in mixed.stderr.decode()
    assert "aws_access_key" not in mixed.stdout.decode()
    assert summary_of(mixed).endswith("1 inline")
    hidden(KEY, mixed)

    (tmp_path / "f.txt").write_text(KEY + " # pasteguard:ignore=\n", encoding="utf-8")
    empty = scan(["f.txt"], cwd=tmp_path)
    assert empty.returncode == 1
    assert "missing a rule name" in empty.stderr.decode()
    assert b"Traceback" not in empty.stderr
    hidden(KEY, empty)

    (tmp_path / "f.txt").write_text(KEY + " # pasteguard:ignore=@@@\n", encoding="utf-8")
    junk = scan(["f.txt"], cwd=tmp_path)
    assert junk.returncode == 1
    assert b"Traceback" not in junk.stderr
    assert "missing a rule name" in junk.stderr.decode()
    hidden(KEY, junk)


def test_unused_ignores(tmp_path):
    text = "# pasteguard:ignore\nhello\n" + KEY + " # pasteguard:ignore\n"
    (tmp_path / "f.txt").write_text(text, encoding="utf-8")
    proc = scan(["--report-unused-ignores", "f.txt"], cwd=tmp_path)
    assert proc.returncode == 1
    body = proc.stdout.decode()
    assert "f.txt:1 unused pasteguard:ignore" in body
    assert "f.txt:3 unused" not in body
    assert "aws_access_key" not in body
    assert summary_of(proc).endswith("1 inline")
    hidden(KEY, proc)

    used = scan(["f.txt"], cwd=tmp_path)
    assert used.returncode == 0
    assert "unused" not in used.stdout.decode()
    hidden(KEY, used)

    (tmp_path / "f.txt").write_text("# pasteguard:ignore\n" + KEY + "\n", encoding="utf-8")
    both = scan(["--report-unused-ignores", "f.txt"], cwd=tmp_path)
    assert both.returncode == 1
    body = both.stdout.decode()
    assert "f.txt:1 unused pasteguard:ignore" in body
    assert "aws_access_key" in body
    hidden(KEY, both)

    (tmp_path / "f.txt").write_text(HF + " # pasteguard:ignore=aws_access_key\n", encoding="utf-8")
    missed = scan(["--report-unused-ignores", "--format", "json", "f.txt"], cwd=tmp_path)
    assert missed.returncode == 1
    rows = json.loads(missed.stdout)
    assert [row["rule"] for row in rows] == ["huggingface_token"]
    assert "unused" not in missed.stdout.decode()
    err = missed.stderr.decode()
    assert "f.txt:1 unused pasteguard:ignore" in err
    assert err.strip().splitlines()[-1].startswith("scanned ")
    hidden(HF, missed)

    (tmp_path / "bare.txt").write_text("# pasteguard:ignore\n", encoding="utf-8")
    stdin = scan(
        ["--report-unused-ignores", "-"],
        input=b"# pasteguard:ignore\n",
        cwd=tmp_path,
    )
    assert stdin.returncode == 1
    assert "-:1 unused pasteguard:ignore" in stdin.stdout.decode()


def test_allowlist_runs_before_inline(tmp_path):
    listed = tmp_path / "allow.txt"
    listed.write_text("value:" + KEY + "\n", encoding="utf-8")
    (tmp_path / "f.txt").write_text(KEY + " # pasteguard:ignore\n", encoding="utf-8")
    env = {"PG_SECRETS_ALLOWLIST": str(listed)}
    proc = scan(["f.txt"], cwd=tmp_path, env=env)
    assert proc.returncode == 0
    assert summary_of(proc) == "scanned 1 file, 0 findings, 0 block, 0 coach, 1 allowlisted, 0 inline"
    hidden(KEY, proc)

    unused = scan(["--report-unused-ignores", "f.txt"], cwd=tmp_path, env=env)
    assert unused.returncode == 1
    assert "f.txt:1 unused pasteguard:ignore" in unused.stdout.decode()
    hidden(KEY, unused)


def test_baseline_and_inline_are_separate(tmp_path):
    (tmp_path / "f.txt").write_text(KEY + " # pasteguard:ignore\n" + HF + "\n", encoding="utf-8")
    base = tmp_path / "base.json"
    wrote = scan(["--write-baseline", str(base), "f.txt"], cwd=tmp_path)
    assert wrote.returncode == 1
    stored = json.loads(base.read_text(encoding="utf-8"))
    assert {item["rule"] for item in stored["findings"]} == {"huggingface_token"}
    blob = base.read_text(encoding="utf-8")
    assert KEY not in blob and HF not in blob

    proc = scan(["--baseline", str(base), "f.txt"], cwd=tmp_path)
    assert proc.returncode == 0
    assert "aws_access_key" not in proc.stdout.decode()
    assert "huggingface" not in proc.stdout.decode()
    assert summary_of(proc) == "scanned 1 file, 0 findings, 0 block, 0 coach, 0 allowlisted, 1 inline, 1 suppressed"
    hidden(KEY, proc)
    hidden(HF, proc)


def test_fail_on_coach_skips_an_inline_password(tmp_path):
    pw = "hunter2" + "-prod-9x"
    (tmp_path / ".env").write_text('DB_PASSWORD="' + pw + '"  # pasteguard:ignore\n', encoding="utf-8")
    proc = scan(["--fail-on", "coach", ".env"], cwd=tmp_path)
    assert proc.returncode == 0
    assert "password_assignment" not in proc.stdout.decode()
    assert summary_of(proc).endswith("1 inline")
    hidden(pw, proc)

    shown = scan(["--fail-on", "coach", "--no-inline-ignore", ".env"], cwd=tmp_path)
    assert shown.returncode == 1
    assert "password_assignment" in shown.stdout.decode()
    hidden(pw, shown)


def test_help_lists_the_flags():
    proc = scan(["--help"])
    text = proc.stdout.decode()
    assert "--no-inline-ignore" in text
    assert "--report-unused-ignores" in text


def test_staged_reads_the_marker_from_the_index(tmp_path):
    repo = init_repo(tmp_path / "repo")
    (repo / "app.txt").write_text("hello\n", encoding="utf-8")
    commit_all(repo, "init")
    (repo / "app.txt").write_text("hello\n" + KEY + "  # pasteguard:ignore\n", encoding="utf-8")
    git(repo, "add", "app.txt")
    # The work tree drops the marker. --staged still reads the index.
    (repo / "app.txt").write_text("hello\n" + KEY + "\n", encoding="utf-8")
    proc = scan(["--staged"], cwd=repo)
    assert proc.returncode == 0
    assert "aws_access_key" not in proc.stdout.decode()
    assert summary_of(proc) == "scanned 1 file, 0 findings, 0 block, 0 coach, 0 allowlisted, 1 inline"
    hidden(KEY, proc)

    # The other way around: the marker exists only in the work tree.
    git(repo, "add", "app.txt")
    (repo / "app.txt").write_text("hello\n" + KEY + "  # pasteguard:ignore\n", encoding="utf-8")
    shown = scan(["--staged"], cwd=repo)
    assert shown.returncode == 1
    assert "aws_access_key" in shown.stdout.decode()
    hidden(KEY, shown)


def test_diff_base_honors_a_marker_on_an_unchanged_line(tmp_path):
    repo = init_repo(tmp_path / "repo")
    (repo / "app.txt").write_text("# pasteguard:ignore-next-line\nplaceholder\n", encoding="utf-8")
    commit_all(repo, "init")
    git(repo, "checkout", "-b", "feature")
    (repo / "app.txt").write_text("# pasteguard:ignore-next-line\n" + KEY + "\n", encoding="utf-8")
    (repo / "new.txt").write_text(HF + " // pasteguard:ignore\n", encoding="utf-8")
    commit_all(repo, "add")
    # The work tree drops the marker. --diff-base still reads the commit.
    (repo / "new.txt").write_text(HF + "\n", encoding="utf-8")

    proc = scan(["--diff-base", "main", "--format", "sarif"], cwd=repo)
    assert proc.returncode == 0, proc.stdout.decode() + proc.stderr.decode()
    results = json.loads(proc.stdout)["runs"][0]["results"]
    assert {row["ruleId"] for row in results} == {"aws_access_key", "huggingface_token"}
    for row in results:
        assert row["suppressions"] == [{"kind": "inSource", "status": "accepted"}]
    aws = next(row for row in results if row["ruleId"] == "aws_access_key")
    assert aws["locations"][0]["physicalLocation"]["region"]["startLine"] == 2
    assert summary_of(proc, "sarif") == "scanned 2 files, 0 findings, 0 block, 0 coach, 0 allowlisted, 2 inline"
    hidden(KEY, proc)
    hidden(HF, proc)

    # Same shape, staged, with the marker already in HEAD and the secret only in the index.
    git(repo, "checkout", "-f", "main")
    (repo / "app.txt").write_text("# pasteguard:ignore-next-line\n" + KEY + "\n", encoding="utf-8")
    git(repo, "add", "app.txt")
    staged = scan(["--staged"], cwd=repo)
    assert staged.returncode == 0
    assert "aws_access_key" not in staged.stdout.decode()
    assert summary_of(staged).endswith("1 inline")
    hidden(KEY, staged)


def test_diff_unused_ignores_follow_added_lines(tmp_path):
    repo = init_repo(tmp_path / "repo")
    (repo / "app.txt").write_text("# pasteguard:ignore=not_a_rule\nhello\n", encoding="utf-8")
    commit_all(repo, "init")
    git(repo, "checkout", "-b", "feature")
    (repo / "app.txt").write_text("# pasteguard:ignore=not_a_rule\nhello\nalso\n", encoding="utf-8")
    commit_all(repo, "add a line")

    quiet = scan(["--diff-base", "main", "--report-unused-ignores"], cwd=repo)
    assert quiet.returncode == 0
    assert b"unknown rule" not in quiet.stderr
    assert "unused" not in quiet.stdout.decode()

    (repo / "app.txt").write_text(
        "# pasteguard:ignore=not_a_rule\nhello\n# pasteguard:ignore\n",
        encoding="utf-8",
    )
    commit_all(repo, "stale marker")
    noisy = scan(["--diff-base", "main", "--report-unused-ignores"], cwd=repo)
    assert noisy.returncode == 1
    assert "app.txt:3 unused pasteguard:ignore" in noisy.stdout.decode()
    assert "app.txt:1 unused" not in noisy.stdout.decode()
    assert "unknown rule" not in noisy.stderr.decode()

    (repo / "app.txt").write_text(
        "hello\n# pasteguard:ignore=not_a_rule\n",
        encoding="utf-8",
    )
    commit_all(repo, "bad rule on an added line")
    warned = scan(["--diff-base", "main"], cwd=repo)
    assert warned.returncode == 0
    assert "unknown rule 'not_a_rule'" in warned.stderr.decode()
    assert b"Traceback" not in warned.stderr
