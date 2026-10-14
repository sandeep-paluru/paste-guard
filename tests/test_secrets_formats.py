"""Format coverage for backend/secrets_scan.py. Fake keys are built at runtime."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.secrets_scan import scan, redact  # noqa: E402

A = "Ab1Cd2Ef3Gh4Ij5Kl6Mn7Op8Qr9St0Uv"  # 32 alnum filler
B = A + "WxYz"  # 36


def types(text):
    return [f["type"] for f in scan(text)]


POSITIVE = [
    ("anthropic_key", "sk" + "-ant-" + "api03-" + A + "_-" + A),
    ("anthropic_key", "sk" + "-ant-" + "admin01-" + A + A),
    ("anthropic_key", "sk" + "-ant-" + "oat01-" + A),
    ("openai_key", "sk" + "-" + A),
    ("openai_key", "sk" + "-proj-" + A + "_" + A),
    ("openai_key", "sk" + "-svcacct-" + A + A),
    ("openai_key", "sk" + "-admin-" + A),
    ("github_pat_fine_grained", "github" + "_pat_" + "11ABCDEFG0" + A + "_" + A),
    ("google_api_key", "AI" + "za" + A + "abc"),
    ("stripe_key", "sk" + "_live_" + A),
    ("stripe_key", "rk" + "_live_" + A),
    ("stripe_key", "sk" + "_test_" + A),
    ("slack_webhook", "https://hooks." + "slack.com/services/" + "T0" + "ABCDEFGH/B0" + "ABCDEFGH/" + A[:24]),
    ("aws_temp_key", "AS" + "IA" + "ABCDEFGHIJKLMNOP"),
    ("jwt", "ey" + "J" + "hbGciOiJIUzI1NiJ9." + "ey" + "J" + "zdWIiOiIxMjM0NTY3ODkwIn0." + "dozjgNryP4J3jVmNHl0w5N"),
    ("huggingface_token", "hf" + "_" + B),
    ("gitlab_token", "gl" + "pat-" + A[:20]),
    ("npm_token", "npm" + "_" + B),
    ("sendgrid_key", "SG" + "." + A[:22] + "." + A + "Abcdefghijk"),
    ("twilio_key", "S" + "K" + "0123456789abcdef0123456789abcdef"),
    ("azure_storage_key", "Account" + "Key=" + A + "abcdefgh+/=="),
    ("db_url_password", "post" + "gres://admin:" + "hunter2pw@db.example.com:5432/app"),
    ("db_url_password", "my" + "sql://root:" + "pw12345@10.0.0.5/app"),
    ("db_url_password", "mongo" + "db+srv://u:" + "pw12345@cluster0.example.net/x"),
    ("xai_key", "xa" + "i-" + A + "abcdefgh"),
    ("google_oauth_client_secret", "GOC" + "SPX-" + A[:28]),
]


@pytest.mark.parametrize("rule,secret", POSITIVE)
def test_positive(rule, secret):
    text = f"config value is {secret} end"
    found = scan(text)
    assert [f["type"] for f in found] == [rule]
    assert text[found[0]["start"]:found[0]["end"]].startswith(secret[:10])


def test_anthropic_not_openai():
    k = "sk" + "-ant-" + "api03-" + A + A
    assert types(k) == ["anthropic_key"]


def test_no_overlap_and_redact():
    k = "sk" + "-ant-" + "api03-" + A + A
    h = "hf" + "_" + B
    text = f"a {k} b {h} c"
    fs = scan(text)
    assert len(fs) == 2
    assert all(a["end"] <= b["start"] for a, b in zip(fs, fs[1:]))
    out = redact(text, fs)
    assert k not in out and h not in out
    assert "[REDACTED:anthropic_key]" in out


def test_longest_wins_on_overlap():
    pw = "pass" + "word = '" + "sk" + "-proj-" + A + "'"
    assert types(pw) == ["password_assignment"]


NEGATIVE = [
    "The quick brown fox jumps over the lazy dog, and the task-force met on Monday.",
    "Please review the risk-assessment-for-the-quarterly-planning-document before Friday.",
    "123e4567-e89b-12d3-a456-426614174000",
    "9fceb02d0ae598e95dc970b74767f19372d61af8",
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk",
    "sk-short",
    "eyJhbGciOiJIUzI1NiJ9 is the header only",
    "postgres://db.example.com:5432/app",
    "https://example.com/services/T000/B000/xyz",
    "hf_short and npm_short and glpat-short",
    "AKIA is a prefix and AIza too",
    "AccountKey=short",
    "SG.too.short",
    "mysql://localhost:3306/app",
]


@pytest.mark.parametrize("text", NEGATIVE)
def test_negative(text):
    assert scan(text) == []


def test_no_catastrophic_backtracking():
    import time
    t = time.time()
    for text in ["sk-" + "a" * 200000, "eyJ" + "a" * 200000, "postgres://" + "a:" * 50000,
                 "AccountKey=" + "A" * 200000 + "!", "github_pat_" + "a" * 200000]:
        scan(text)
    assert time.time() - t < 5


def test_anthropic_key_blocks_end_to_end():
    """A pasted Anthropic key is a hard block in the real backend, not just a scanner hit."""
    import app
    key = "sk-ant-" + "api03-" + "Ab3dE" * 18 + "-xyzAA"
    out = app.decide("Here is my config, why does it fail?\nANTHROPIC_API_KEY=" + key)
    assert out["verdict"] == "block"
    assert key not in out["redacted"]
