"""Format coverage for backend/secrets_scan.py. Fake keys are built at runtime."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.secrets_scan import scan, redact  # noqa: E402

A = "Ab1Cd2Ef3Gh4Ij5Kl6Mn7Op8Qr9St0Uv"  # 32 alnum filler
B = A + "WxYz"  # 36
# Public AWS sample secret, split so the literal is not contiguous in the repo.
AWS_SECRET = "wJalr" + "XUtnFEMI/" + "K7MDENG/" + "bPxRfiCY" + "EXAMPLEKEY"


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
    ("db_url_password", "re" + "dis://:" + "hunter2pw@redis.example.com:6379/0"),
    ("db_url_password", "re" + "diss://app:" + "pw12345@cache.example.com:6380"),
    ("db_url_password", "am" + "qp://guest:" + "pw12345@rabbit.example.com:5672/%2F"),
    ("db_url_password", "am" + "qps://guest:" + "pw12345@rabbit.example.com:5671/app"),
    ("db_url_password", "ms" + "sql://sa:" + "pw12345@db.example.com:1433/app"),
    ("db_url_password", "ms" + "sql+pyodbc://sa:" + "pw12345@db.example.com/app"),
    ("db_url_password", "sql" + "server://sa:" + "pw12345@db.example.com:1433"),
    ("password_assignment", "DB_PASSWORD=" + "hunter2-prod-9x"),
    ("password_assignment", "passwd=" + "hunter2-prod-9x"),
    ("password_assignment", "export AWS_SECRET_ACCESS_KEY=" + AWS_SECRET),
    ("password_assignment", "export DB_PASSWORD='" + "hunter2-prod-9x" + "'"),
    ("password_assignment", "client_secret: " + "8f3k2" + A),
    ("password_assignment", "access_token = " + "abc" + A),
    ("password_assignment", "access_token=" + "abcdefghijklmnop"),
    ("password_assignment", "auth_token=" + "aa91" + B),
    ("password_assignment", "private_key_id: " + "kid" + A[:20]),
    ("password_assignment", "MY_API_KEY=" + "k9" + A),
    ("password_assignment", '"api_key": "' + "k9" + A + '"'),
    ("password_assignment", 'password = "correcthorse"'),
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


def test_specific_rule_wins_over_generic_on_overlap():
    # A real key inside password = '...' is reported as the key (a hard block), not the generic coach rule.
    pw = "pass" + "word = '" + "sk" + "-proj-" + A + "'"
    assert types(pw) == ["openai_key"]


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
    "DB_PASSWORD=",
    'DB_PASSWORD=""',
    "secret: ''",
    "DB_PASSWORD=${DB_PASSWORD}",
    "export AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}",
    "DB_PASSWORD=$DB_PASSWORD",
    "client_secret: ${CLIENT_SECRET}",
    "password: <your-password>",
    'password = "<your-password>"',
    'password = "changeme"',
    "api_key = 'change_me'",
    "api_key = 'change-me'",
    'api_key = "xxxx"',
    'api_key = "xxxxxxxx"',
    'secret: "***"',
    'secret = "******"',
    "api_key: your_api_key_here",
    'api_key = "your_api_key_here"',
    "password=example",
    'password = "example"',
    "client_secret: example_key",
    "client_secret: null",
    'api_key = "null"',
    "auth_token: None",
    'private_key_id = "None"',
    "password = None",
    "DB_PASSWORD=abc",
    'password = "short"',
    "access_token = abc",
    "the password policy is: rotate every 90 days",
    "password: rotate every 90 days",
    "the secretary: hunter2-prod-9x is not a key name",
    "redis://localhost:6379/0",
    "rediss://cache.example.com:6380",
    "amqp://rabbit.example.com:5672",
    "amqps://rabbit.example.com:5671",
    "mssql://db.example.com/app",
    "sqlserver://db.example.com:1433",
    "postgres://user:changeme@db.example.com/app",
    "redis://:example@localhost:6379",
    "redis://:${REDIS_PASSWORD}@localhost:6379",
]


@pytest.mark.parametrize("text", NEGATIVE)
def test_negative(text):
    assert scan(text) == []


def test_no_catastrophic_backtracking():
    import time
    t = time.time()
    for text in ["sk-" + "a" * 200000, "eyJ" + "a" * 200000, "postgres://" + "a:" * 50000,
                 "redis://" + "a:" * 50000, "AccountKey=" + "A" * 200000 + "!",
                 "github_pat_" + "a" * 200000, "DB_PASSWORD=" + "a" * 200000,
                 "password " + "a" * 200000]:
        scan(text)
    assert time.time() - t < 5


def test_anthropic_key_blocks_end_to_end():
    """A pasted Anthropic key is a hard block in the real backend, not just a scanner hit."""
    import app
    key = "sk-ant-" + "api03-" + "Ab3dE" * 18 + "-xyzAA"
    out = app.decide("Here is my config, why does it fail?\nANTHROPIC_API_KEY=" + key)
    assert out["verdict"] == "block"
    assert key not in out["redacted"]


def test_specific_key_beats_generic_assignment():
    # api_key="<anthropic key>" used to be reported as the generic password_assignment (coach only)
    key = "sk-ant-" + "api03-" + "Ab3dE" * 18 + "-xyzAA"
    for line in (f'client = Anthropic(api_key="{key}")', f"api_key = '{key}'", f'secret: "{key}"'):
        assert [f["type"] for f in scan(line)] == ["anthropic_key"], line
    assert [f["type"] for f in scan('password = "hunter22-not-a-key"')] == ["password_assignment"]


def test_env_provider_key_beats_generic():
    key = "sk" + "-proj-" + A
    assert types("OPENAI_API_KEY=" + key) == ["openai_key"]
    assert types("export OPENAI_API_KEY='" + key + "'") == ["openai_key"]


def test_db_url_beats_password_assignment():
    url = "re" + "dis://:" + "hunter2pw@redis.example.com:6379/0"
    assert types("DB_PASSWORD=" + url) == ["db_url_password"]


def test_assignment_redact_replaces_the_whole_assignment():
    # The span is the whole assignment, same as the quoted password rule, so redact()
    # removes the name and the value together.
    val = "hunter2-prod-9x"
    text = "use DB_PASSWORD=" + val + " today"
    found = scan(text)
    assert [f["type"] for f in found] == ["password_assignment"]
    assert text[found[0]["start"]:found[0]["end"]] == "DB_PASSWORD=" + val
    out = redact(text, found)
    assert val not in out and "DB_PASSWORD=" not in out
    assert out == "use [REDACTED:password_assignment] today"
    quoted = 'password = "hunter22-not-a-key"'
    assert redact(quoted, scan(quoted)) == "[REDACTED:password_assignment]"


def test_two_env_lines_redact_both():
    first = "hunter2-prod-9x"
    second = "8f3k2" + A
    text = "DB_PASSWORD=" + first + "\nclient_secret: " + second + "\n"
    fs = scan(text)
    assert [f["type"] for f in fs] == ["password_assignment", "password_assignment"]
    out = redact(text, fs)
    assert first not in out and second not in out
    assert out.count("[REDACTED:password_assignment]") == 2
