"""Live log: /logs page, /logs/api feed and console line. Never contains the pasted text."""
import os
import sys

os.environ.setdefault("PG_NO_WARMUP", "1")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from fastapi.testclient import TestClient  # noqa: E402

import app as appmod  # noqa: E402
import livelog  # noqa: E402

client = TestClient(appmod.app)
MEMO = ("Ferrolake reported trailing twelve month revenue of 6.2 million dollars with 71 percent gross margin "
        "and net revenue retention of 118 percent. The company burns roughly 480,000 dollars per month and has "
        "7 months of runway, which gives us meaningful leverage on price.")


def _last():
    return client.get("/logs/api").json()["events"][-1]


def test_logs_page_served():
    r = client.get("/logs")
    assert r.status_code == 200 and "/logs/api" in r.text and "live checks" in r.text


def test_check_appears_with_scores_and_no_text():
    before = client.get("/logs/api").json()["events"]
    after = before[-1]["id"] if before else 0
    client.post("/check", json={"text": MEMO, "source": "chatgpt.com"})
    ev = client.get(f"/logs/api?after={after}").json()["events"]
    assert len(ev) == 1
    e = ev[0]
    assert e["verdict"] in {"block", "coach"} and e["site"] == "chatgpt.com" and e["channel"] == "paste"
    assert e["source"] and "ferrolake" in e["source"]
    assert set(e["scores"]) == {"embedding", "ngram", "tfidf"}
    assert e["ms"] >= 0 and len(e["hash"]) == 10 and e["chars"] == len(MEMO)
    assert "Ferrolake" not in str(e) and "runway" not in str(e)


def test_fast_path_flag_for_benign_paste():
    client.post("/check", json={"text": "What is a good recipe for banana bread with walnuts and a little cinnamon?"})
    e = _last()
    assert e["verdict"] == "allow" and e["minilm_skipped"] is True and e["path"] == "cheap_clear"
    assert "banana" not in str(e)


def test_short_paste_logged():
    client.post("/check", json={"text": "hi"})
    e = _last()
    assert e["path"] == "short" and e["verdict"] == "allow"


def test_file_upload_logged_as_file():
    client.post("/check_file", files={"file": ("memo.txt", MEMO.encode(), "text/plain")}, data={"source": "claude.ai"})
    e = _last()
    assert e["channel"] == "file" and e["file"] == "memo.txt" and e["site"] == "claude.ai"


def test_after_cursor_and_console_line(capsys):
    n = client.get("/logs/api").json()["events"][-1]["id"] if client.get("/logs/api").json()["events"] else 0
    assert client.get(f"/logs/api?after={n}").json()["events"] == []
    line = livelog.line(_last() if n else {"time": "00:00:00", "verdict": "allow", "channel": "paste", "site": "x",
                        "scores": {"embedding": None, "ngram": None, "tfidf": None}, "minilm_skipped": True,
                        "ms": 1, "hash": "abc", "chars": 3, "source": None, "secrets": []})
    assert "ms" in line and "#" in line and "\n" not in line


def test_logs_local_only():
    r = TestClient(appmod.app, client=("10.0.0.5", 1234)).get("/logs/api")
    assert r.status_code == 403
