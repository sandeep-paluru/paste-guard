"""Demo pages served by the backend: /demo/compare (regex baseline vs Paste Guard) and /demo/redteam.

Everything runs offline against local files: demo/compare/examples.json, demo/redteam/rewrites.json and the
existing eval results (eval/bench_summary.json, eval/bench/fastpath.json). No external requests, no API key.
"""
import json
import time
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from config import ROOT, VERSION
from regex_baseline import regex_flag, regex_reasons

HERE = Path(__file__).parent
EXAMPLES = ROOT / "demo" / "compare" / "examples.json"
REWRITES = ROOT / "demo" / "redteam" / "rewrites.json"
SUMMARY = ROOT / "eval" / "bench_summary.json"
FASTPATH = ROOT / "eval" / "bench" / "fastpath.json"
EVAL_DATA = ROOT / "eval" / "data"
FLAGGED = ("coach", "block")  # what the eval counts as caught


def _load(path: Path, what: str):
    if not path.exists():
        raise HTTPException(404, f"{what} not found ({path.relative_to(ROOT)}); this install does not ship the demo data")
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def eval_regex_by_type() -> dict:
    """{transform: [pastes, flagged by the regex baseline]} over all eval pastes (regex only, a few ms)."""
    out: dict = {}
    for f in ("doc", "code"):
        p = EVAL_DATA / f"{f}_pastes.jsonl"
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                if r["label"] == "positive":
                    c = out.setdefault(r["transform"], [0, 0])
                    c[0] += 1
                    c[1] += regex_flag(r["text"])
    return out


def eval_totals() -> dict | None:
    """Headline numbers read from the existing eval result files (None if they are not shipped)."""
    if not (SUMMARY.exists() and FASTPATH.exists()):
        return None
    s = json.loads(SUMMARY.read_text())["regex"]
    fp = json.loads(FASTPATH.read_text())["all"]["on"]
    tp = sum(s[k]["in"]["tp"] for k in ("doc", "code"))
    fn = sum(s[k]["in"]["fn"] for k in ("doc", "code"))
    fpos = sum(s[k]["in"]["fp"] for k in ("doc", "code"))
    tn = sum(s[k]["in"]["tn"] for k in ("doc", "code"))
    return {"pastes": fp["n"], "positives": tp + fn,
            "regex": {"recall": tp / (tp + fn), "doc_recall": s["doc"]["in"]["recall"], "code_recall": s["code"]["in"]["recall"],
                      "fpr": fpos / (fpos + tn)},
            "paste_guard": {"recall": fp["recall"], "fpr": fp["fpr"], "p50_ms": fp["p50"], "p95_ms": fp["p95"]}}


def make_router(decide) -> APIRouter:
    router = APIRouter()

    @router.get("/demo/compare", response_class=HTMLResponse)
    def compare_page():
        return (HERE / "demo_compare.html").read_text(encoding="utf-8")

    @router.get("/demo/compare/api")
    def compare_api():
        data = _load(EXAMPLES, "examples")
        by_type = eval_regex_by_type()
        rows = []
        for ex in data["examples"]:
            reasons = regex_reasons(ex["text"])
            t0 = time.perf_counter()
            res = decide(ex["text"])
            ms = (time.perf_counter() - t0) * 1000
            top = res.get("semantic_match")
            n, hit = by_type.get(ex.get("eval_transform"), [0, 0])
            rows.append({
                "id": ex["id"], "type": ex["type"], "text": ex["text"], "origin": ex["origin"], "expected": ex["expected"],
                "regex": {"flagged": bool(reasons), "verdict": "flagged" if reasons else "missed", "reasons": reasons[:4],
                          "eval_flagged": hit, "eval_total": n},
                "paste_guard": {"verdict": res["verdict"], "flagged": res["verdict"] in FLAGGED, "message": res["message"],
                                "doc": (top or {}).get("path"), "method": (top or {}).get("method"),
                                "similarity": (top or {}).get("similarity"),
                                "secrets": [f["type"] for f in res["findings"]][:3], "ms": round(ms, 1)}})
        return {"version": VERSION, "note": data.get("note", ""), "totals": eval_totals(), "examples": rows}

    return router
