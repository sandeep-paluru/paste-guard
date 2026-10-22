"""Known-safe secret allowlist: exact values, regexes, and sha256 fingerprints."""
import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

os.environ.setdefault("PG_NO_WARMUP", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from fastapi.testclient import TestClient  # noqa: E402

import app  # noqa: E402
import config  # noqa: E402
import livelog  # noqa: E402
from secrets_scan import (  # noqa: E402
    apply_allowlist,
    compile_allowlist,
    fingerprint_bytes,
    public_examples,
    scan,
)

ROOT = Path(__file__).resolve().parents[1]
client = TestClient(app.app)


def _types(text):
    return [f["type"] for f in scan(text)]


def _allow(entries, examples=False, file=""):
    return compile_allowlist({"examples": examples, "allowlist": list(entries), "file": file})


STRIPE = "sk" + "_test_" + "Ab1Cd2Ef3Gh4Ij5Kl6"
STRIPE_NEAR = STRIPE[:-1] + "7"
REAL = "sk" + "-ant-" + "api03-" + "Ab3dE" * 18 + "-xyzAA"


def test_exact_value_suppresses_hit():
    allow = _allow(["value:" + STRIPE])
    kept, n = apply_allowlist("token " + STRIPE, scan("token " + STRIPE), allow)
    assert n == 1 and kept == []
    kept, n = apply_allowlist("token " + STRIPE_NEAR, scan("token " + STRIPE_NEAR), allow)
    assert n == 0 and [f["type"] for f in kept] == ["stripe_key"]


def test_regex_suppresses_hit_and_near_miss_does_not():
    allow = _allow(["regex:" + STRIPE])
    kept, n = apply_allowlist("token " + STRIPE, scan("token " + STRIPE), allow)
    assert n == 1 and kept == []
    # A pattern must match the whole value. A fragment does not suppress a real key.
    fragment = _allow(["regex:Ab1Cd2"])
    assert not fragment.matches(STRIPE)
    kept, n = apply_allowlist("token " + STRIPE_NEAR, scan("token " + STRIPE_NEAR), allow)
    assert n == 0 and [f["type"] for f in kept] == ["stripe_key"]


def test_fingerprint_suppresses_hit_and_near_miss_does_not():
    digest = hashlib.sha256(STRIPE.encode()).hexdigest()
    allow = _allow(["sha256:" + digest.upper()])  # hex case is ignored
    kept, n = apply_allowlist("token " + STRIPE, scan("token " + STRIPE), allow)
    assert n == 1 and kept == []
    kept, n = apply_allowlist("token " + STRIPE_NEAR, scan("token " + STRIPE_NEAR), allow)
    assert n == 0 and kept and kept[0]["type"] == "stripe_key"


def test_assignment_matches_the_password_not_only_the_line():
    secret = "hunter2-prod-9x"
    digest = hashlib.sha256(secret.encode()).hexdigest()
    allow = _allow(["sha256:" + digest])
    for text in ("DB_PASSWORD=" + secret, 'password = "' + secret + '"'):
        kept, n = apply_allowlist(text, scan(text), allow)
        assert kept == [] and n == 1, text
    # The digest is of the password, not the whole assignment.
    assert digest != hashlib.sha256(("DB_PASSWORD=" + secret).encode()).hexdigest()
    near = "export AWS_SECRET_ACCESS_KEY=" + public_examples()[1][:-1] + "Z"
    kept, n = apply_allowlist(near, scan(near), compile_allowlist({"examples": True, "allowlist": [], "file": ""}))
    assert n == 0 and [f["type"] for f in kept] == ["password_assignment"]


def test_public_examples_still_detected_then_suppressed():
    akia, secret, stripe, jwt = public_examples()
    allow = compile_allowlist({"examples": True, "allowlist": [], "file": ""})
    samples = [
        (akia, ["aws_access_key"]),
        (stripe, ["stripe_key"]),
        (jwt, ["jwt"]),
        ("AWS_SECRET_ACCESS_KEY=" + secret, ["password_assignment"]),
    ]
    for text, types in samples:
        assert _types(text) == types
        kept, n = apply_allowlist(text, scan(text), allow)
        assert kept == [] and n == 1
    near = stripe[:-1] + ("d" if stripe[-1] != "d" else "e")
    assert _types(near) == ["stripe_key"]
    kept, n = apply_allowlist(near, scan(near), allow)
    assert n == 0 and kept


def test_documented_sample_does_not_block_and_another_test_key_does():
    akia, _, stripe, _jwt = public_examples()
    sample = app.decide("docs show " + akia + " and " + stripe)
    assert sample["allowlisted"] == 2
    assert sample["verdict"] == "allow"
    assert not any(f["type"] in {"aws_access_key", "stripe_key"} for f in sample["findings"])
    other = "sk" + "_test_" + "Zz9Ab1Cd2Ef3Gh4Ij5K"
    blocked = app.decide("pay " + other)
    assert blocked["verdict"] == "block" and blocked["allowlisted"] == 0
    assert any(f["type"] == "stripe_key" for f in blocked["findings"])
    assert other not in blocked["redacted"]


def test_near_miss_value_still_blocks():
    akia = public_examples()[0]
    near = akia[:-1] + "F"
    assert near != akia
    out = app.decide(near)
    assert out["verdict"] == "block" and out["allowlisted"] == 0
    assert any(f["type"] == "aws_access_key" for f in out["findings"])
    assert near not in out["redacted"]


def test_one_allowlisted_and_one_real_key_still_blocks():
    safe = public_examples()[0]
    text = "sample " + safe + "\nreal " + REAL
    out = app.decide(text)
    assert out["verdict"] == "block"
    assert out["allowlisted"] == 1
    assert [f["type"] for f in out["findings"]] == ["anthropic_key"]
    assert REAL not in out["redacted"]
    assert safe not in out["message"]
    r = client.post("/check", json={"text": text, "source": "chatgpt.com"})
    body = r.json()
    assert body["verdict"] == "block" and body["allowlisted"] == 1
    ev = client.get("/logs/api").json()["events"][-1]
    assert ev["allowlisted"] == 1 and "anthropic_key" in ev["secrets"]
    line = livelog.line(ev)
    assert "allowlisted: 1" in line
    assert safe not in line and REAL not in line
    assert safe not in str(ev) and REAL not in str(ev)


def test_logs_page_mentions_the_count():
    assert "allowlisted:" in client.get("/logs").text


def test_file_comments_and_bad_lines(tmp_path):
    digest = "ab" * 32
    path = tmp_path / "allow.txt"
    path.write_text(
        "# comment\n"
        "\n"
        "value:throwaway-key-1\n"
        "regex:demo_[0-9]{4}\n"
        "sha256:" + digest + "\n"
        "this line is bad\n"
        "regex:[\n"
        "sha256:zzzz\n"
        "value:\n"
        "  # indented comment\n",
        encoding="utf-8",
    )
    allow = _allow([], file=str(path))
    assert "throwaway-key-1" in allow.values
    assert allow.matches("demo_1234") and not allow.matches("demo_12345")
    assert digest in allow.hashes
    assert len(allow.bad) == 4
    assert not any("comment" in item for item in allow.bad)
    # A line with no prefix is not treated as a secret value.
    bare = tmp_path / "bare.txt"
    bare.write_text(public_examples()[0] + "\n")
    bare_allow = _allow([], file=str(bare))
    assert bare_allow.bad and not bare_allow.matches(public_examples()[0])


def test_config_loads_file_and_env_override(tmp_path, monkeypatch):
    listed = tmp_path / "allow.txt"
    listed.write_text("# keep\nvalue:from-file\nnot a real entry\n", encoding="utf-8")
    other = tmp_path / "other.txt"
    other.write_text("value:from-env\n", encoding="utf-8")
    toml = tmp_path / "paste-guard.toml"
    toml.write_text('[secrets]\nexamples = false\nallowlist = ["value:from-toml"]\nfile = "allow.txt"\n')
    monkeypatch.setattr(config, "CONFIG_PATH", toml)
    cfg = config.load()
    assert cfg["secrets"]["examples"] is False
    assert cfg["secrets"]["file"] == str(listed.resolve())
    assert cfg["secrets"]["allowlist"] == ["value:from-toml"]
    allow = compile_allowlist(cfg["secrets"])
    assert allow.matches("from-file") and allow.matches("from-toml")
    assert allow.bad and not allow.matches(public_examples()[0])

    monkeypatch.setenv("PG_SECRETS_ALLOWLIST", str(other))
    monkeypatch.setenv("PG_SECRETS_EXAMPLES", "false")
    cfg = config.load()
    assert cfg["secrets"]["file"] == str(other.resolve())
    assert cfg["secrets"]["examples"] is False
    allow = compile_allowlist(cfg["secrets"])
    assert allow.matches("from-env") and not allow.matches("from-file")


def test_missing_allowlist_file_exits(tmp_path):
    missing = tmp_path / "missing.txt"
    with pytest.raises(SystemExit, match="not found"):
        compile_allowlist({"examples": False, "allowlist": [], "file": str(missing)})


def test_fingerprint_helper():
    key = STRIPE
    assert fingerprint_bytes(key.encode() + b"\n") == hashlib.sha256(key.encode()).hexdigest()
    assert fingerprint_bytes(key.encode() + b"\r\n") == hashlib.sha256(key.encode()).hexdigest()
    assert fingerprint_bytes(key.encode() + b"\n\n") == hashlib.sha256((key + "\n").encode()).hexdigest()
    proc = subprocess.run(
        [sys.executable, str(ROOT / "backend" / "secrets_scan.py")],
        input=key.encode() + b"\n", capture_output=True, check=True)
    digest = proc.stdout.decode().strip()
    assert digest == hashlib.sha256(key.encode()).hexdigest()
    script = subprocess.run(
        [str(ROOT / "pasteguard"), "fingerprint"],
        input=key.encode() + b"\n", capture_output=True, check=True)
    assert script.stdout.decode().strip() == digest
    allow = _allow(["sha256:" + digest])
    kept, n = apply_allowlist("token " + key, scan("token " + key), allow)
    assert kept == [] and n == 1
    usage = subprocess.run(
        [sys.executable, str(ROOT / "backend" / "secrets_scan.py"), "nope"],
        input=b"x", capture_output=True)
    assert usage.returncode == 2


def test_shipped_examples_flag_can_be_turned_off(monkeypatch):
    monkeypatch.delenv("PG_SECRETS_EXAMPLES", raising=False)
    monkeypatch.delenv("PG_SECRETS_ALLOWLIST", raising=False)
    cfg = config.load()
    assert cfg["secrets"]["examples"] is True
    assert cfg["secrets"]["allowlist"] == []
    assert cfg["secrets"]["file"] == ""
    monkeypatch.setenv("PG_SECRETS_EXAMPLES", "0")
    assert config.load()["secrets"]["examples"] is False
