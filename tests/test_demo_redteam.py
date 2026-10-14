"""/demo/redteam page, the pre-generated rewrites file, and the API (real model for the replay test)."""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from fastapi.testclient import TestClient  # noqa: E402

import app  # noqa: E402
import demo_pages  # noqa: E402

client = TestClient(app.app)
FILE = ROOT / "demo" / "redteam" / "rewrites.json"


def test_rewrites_file_loads_and_is_labelled_synthetic():
    d = json.loads(FILE.read_text(encoding="utf-8"))
    assert d["note"].lower().startswith("generated in advance by claude (anthropic) for demo; labelled synthetic")
    assert d["synthetic"] is True and d["source_doc"] == "board-memo-acquisition-ferrolake.md"
    assert (ROOT / "demo" / "company-docs" / d["source_doc"]).exists()
    rows = d["rewrites"]
    assert 25 <= len(rows) <= 60
    assert len({r["id"] for r in rows}) == len(rows)
    assert all(r["technique"] and len(r["text"]) > 20 for r in rows)
    assert not any("—" in r["text"] or "—" in r["technique"] for r in rows)
    techniques = " ".join(r["technique"].lower() for r in rows)
    for needle in ("paraphrase", "summary", "translation", "bullet", "synonym", "typo", "homoglyph", "splitting"):
        assert needle in techniques, needle


def test_api_serves_the_file():
    d = client.get("/demo/redteam/api").json()
    assert d["count"] == len(d["rewrites"]) >= 25
    assert "labelled synthetic" in d["note"]
    assert d["rewrites"][0] == json.loads(FILE.read_text(encoding="utf-8"))["rewrites"][0]


def test_api_is_404_when_demo_data_is_not_shipped(monkeypatch, tmp_path):
    monkeypatch.setattr(demo_pages, "REWRITES", tmp_path / "missing.json")
    assert client.get("/demo/redteam/api").status_code == 404


def test_page_is_offline_and_uses_check():
    r = client.get("/demo/redteam")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    assert "/demo/redteam/api" in r.text and '"/check"' in r.text
    assert not re.search(r"""(src|href)\s*=\s*["']https?://""", r.text)
    assert "—" not in r.text and "ANTHROPIC_API_KEY" not in r.text


def test_replaying_rewrites_through_check_gives_a_real_mix():
    rows = client.get("/demo/redteam/api").json()["rewrites"][:12]
    verdicts = [client.post("/check", json={"text": r["text"], "source": "demo/redteam"}).json()["verdict"] for r in rows]
    assert all(v in {"allow", "nudge", "coach", "block"} for v in verdicts)
    assert sum(v in ("coach", "block") for v in verdicts) >= 6  # the first dozen are mostly direct rewrites of the memo
