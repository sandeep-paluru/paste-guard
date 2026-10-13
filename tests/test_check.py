"""End-to-end tests against the real model and real index (no mocks)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from fastapi.testclient import TestClient  # noqa: E402

import app  # noqa: E402

client = TestClient(app.app)

# Renamed and reformatted copy of base64_decode from itsdangerous/encoding.py
DISGUISED = '''
def decode_b64_safe(data):
    data = to_bytes(data, encoding="ascii", errors="ignore")
    data += b"=" * (-len(data) % 4)
    try:
        return base64.urlsafe_b64decode(data)
    except (TypeError, ValueError) as err:
        raise DecodeError("Invalid base64-encoded data") from err
'''

UNRELATED = '''
def bubble_sort(items):
    n = len(items)
    for i in range(n):
        for j in range(0, n - i - 1):
            if items[j] > items[j + 1]:
                items[j], items[j + 1] = items[j + 1], items[j]
    return items
'''

SECRET = 'client = boto3.client("s3", aws_access_key_id="AKIAABCDEFGHIJKLMNOP")\nprint(client.list_buckets())'


def run(name, text):
    r = client.post("/check", json={"text": text}).json()
    m = r["semantic_match"]
    print(f"{name:10s} verdict={r['verdict']:6s} sim={m['similarity'] if m else None} "
          f"path={m['path'] if m else None}")
    return r


def test_disguised_matches():
    r = run("disguised", DISGUISED)
    assert r["verdict"] in {"coach", "block"}
    assert r["semantic_match"]["path"].endswith("encoding.py")
    assert "[REDACTED:company_code" in r["redacted"]


def test_unrelated_allows():
    assert run("unrelated", UNRELATED)["verdict"] == "allow"


def test_secret_blocks():
    r = run("secret", SECRET)
    assert r["verdict"] == "block" and "AKIA" not in r["redacted"]


if __name__ == "__main__":
    print(client.get("/health").json())
    test_disguised_matches(); test_unrelated_allows(); test_secret_blocks(); print("ALL PASS")
