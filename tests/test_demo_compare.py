"""/demo/compare page and API (real model, real index)."""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "eval"))
from fastapi.testclient import TestClient  # noqa: E402

import app  # noqa: E402

client = TestClient(app.app)


def test_page_is_self_contained_html():
    r = client.get("/demo/compare")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    assert "/demo/compare/api" in r.text
    assert not re.search(r"""(src|href)\s*=\s*["']https?://""", r.text), "page must work offline, no CDNs"
    assert "—" not in r.text and "–" not in r.text


def test_api_rows_cover_the_fixed_example_types():
    d = client.get("/demo/compare/api").json()
    assert [e["type"] for e in d["examples"]] == ["Verbatim", "Paraphrase", "Partial excerpt", "Summary",
                                                  "Code, renamed and reformatted", "Secret", "Benign"]
    for e in d["examples"]:
        assert set(e["regex"]) >= {"flagged", "verdict", "reasons"}
        assert e["paste_guard"]["verdict"] in {"allow", "nudge", "coach", "block"} and e["paste_guard"]["ms"] >= 0
    by = {e["type"]: e for e in d["examples"]}
    for t in ("Verbatim", "Paraphrase", "Partial excerpt", "Summary"):
        assert by[t]["paste_guard"]["flagged"] and by[t]["paste_guard"]["doc"], t
    assert not by["Paraphrase"]["regex"]["flagged"]  # the point of the demo
    assert by["Secret"]["regex"]["flagged"] and by["Secret"]["paste_guard"]["verdict"] == "block"
    assert by["Benign"]["paste_guard"]["verdict"] == "allow" and not by["Benign"]["regex"]["flagged"]


def test_api_totals_come_from_the_eval_files_not_constants():
    d = client.get("/demo/compare/api").json()
    t = d["totals"]
    summary = json.loads((ROOT / "eval" / "bench_summary.json").read_text())["regex"]
    tp = summary["doc"]["in"]["tp"] + summary["code"]["in"]["tp"]
    fn = summary["doc"]["in"]["fn"] + summary["code"]["in"]["fn"]
    assert abs(t["regex"]["recall"] - tp / (tp + fn)) < 1e-9
    assert abs(t["regex"]["doc_recall"] - summary["doc"]["in"]["recall"]) < 1e-9
    fast = json.loads((ROOT / "eval" / "bench" / "fastpath.json").read_text())["all"]["on"]
    assert t["paste_guard"]["recall"] == fast["recall"] and t["pastes"] == fast["n"]
    assert 0.08 < t["regex"]["recall"] < 0.15 and t["paste_guard"]["recall"] > 0.9


def test_baseline_is_the_eval_baseline():
    import baseline  # eval/baseline.py re-exports the backend module, so there is one implementation
    import regex_baseline
    assert baseline.regex_flag is regex_baseline.regex_flag
    assert regex_baseline.regex_reasons("see the Term Sheet") == ["keyword: term sheet"]
    assert regex_baseline.regex_reasons("a plain sentence about lunch") == []
