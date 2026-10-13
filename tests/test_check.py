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


DOC_ROOT = Path(__file__).resolve().parents[1] / "demo" / "company-docs"


def _doc_paraphrase():
    import json
    rows = [json.loads(l) for l in open(Path(__file__).resolve().parents[1] / "eval" / "data" / "doc_pastes.jsonl")]
    return next(r for r in rows if r["transform"] == "paraphrase" and r["label"] == "positive")


def test_doc_paraphrase_caught_with_passage():
    r0 = _doc_paraphrase()
    r = run("doc-para", r0["text"])
    m = r["semantic_match"]
    assert r["verdict"] in {"nudge", "coach", "block"}
    assert m["kind"] == "doc" and m["snippet"] and m["source"]


def test_public_prose_allows():
    text = ("The mitochondria is the powerhouse of the cell. Cellular respiration converts glucose and oxygen "
            "into carbon dioxide, water and ATP, which the cell uses as an energy source for most processes.")
    assert run("public", text)["verdict"] == "allow"


def test_confidential_marker_coaches():
    r = run("marker", "CONFIDENTIAL. Please summarise the attached notes about our weekend volunteering event plans.")
    assert r["verdict"] == "coach"


def test_check_file_docx_and_pdf():
    for name in ("ma-term-sheet-ferrolake.docx", "layoff-plan-q4-2026.pdf"):
        p = DOC_ROOT / name
        r = client.post("/check_file", files={"file": (name, p.read_bytes())}).json()
        print(name, r["verdict"], r["semantic_match"]["source"])
        assert r["verdict"] == "block" and r["semantic_match"]["source"] == name


def test_check_file_rejects_unknown_type():
    assert client.post("/check_file", files={"file": ("x.exe", b"MZ")}).status_code == 415


def test_admin_logs_no_content():
    client.post("/check", json={"text": SECRET, "source": "claude.ai"})
    d = client.get("/admin/api").json()
    assert d["recent"] and "AKIA" not in str(d["recent"])
    assert client.get("/admin").status_code == 200


if __name__ == "__main__":
    print(client.get("/health").json())
    test_disguised_matches(); test_unrelated_allows(); test_secret_blocks(); print("ALL PASS")
