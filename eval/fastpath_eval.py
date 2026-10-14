"""End-to-end effect of the two-step fast path on the real backend logic (app.decide).

  python eval/fastpath_eval.py [--out eval/bench/fastpath.json]

Every eval paste goes through decide() twice in the same process, once with the fast path off
(MiniLM on every paste) and once on. A paste counts as flagged when the verdict is coach or block.
Reports recall, false alarm rate, p50/p95 latency per mode and per held-out fold (bench_report.folds),
how often MiniLM was skipped, and any paste whose verdict changed.
"""
import argparse, json, sys, time
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend")); sys.path.insert(0, str(ROOT / "eval"))
import app  # noqa: E402
from bench_report import folds  # noqa: E402

ap = argparse.ArgumentParser(); ap.add_argument("--out", default="eval/bench/fastpath.json"); a = ap.parse_args()
samples = []
for f in ("doc", "code"):
    for line in (ROOT / "eval" / "data" / f"{f}_pastes.jsonl").read_text().splitlines():
        if line.strip():
            r = json.loads(line); r["kind"] = f; samples.append(r)
app.decide("warm up the model once before timing anything")


def run(on):
    app.FAST["enabled"] = on
    out = {}
    for r in samples:
        app.STATS["last_path"] = None
        t0 = time.perf_counter(); v = app.decide(r["text"])["verdict"]; ms = (time.perf_counter() - t0) * 1000
        out[r["id"]] = {"verdict": v, "ms": ms, "path": app.STATS.get("last_path")}
    return out


def metrics(res, ids):
    pos = [i for i in ids if lab[i] == "positive"]; neg = [i for i in ids if lab[i] != "positive"]
    fl = lambda i: res[i]["verdict"] in ("coach", "block")  # noqa: E731
    lat = [res[i]["ms"] for i in ids]
    return {"n": len(ids), "recall": sum(map(fl, pos)) / len(pos), "fpr": sum(map(fl, neg)) / len(neg) if neg else 0.0,
            "p50": float(np.percentile(lat, 50)), "p95": float(np.percentile(lat, 95)),
            "skipped": sum(res[i]["path"] in ("cheap_block", "cheap_clear") for i in ids) / len(ids)}


lab = {r["id"]: r["label"] for r in samples}
off, on = run(False), run(True)
off, on = run(False), run(True)  # second pass: timings after both paths are warm
rep = {}
for kind in ("doc", "code"):
    sub = [r for r in samples if r["kind"] == kind]
    fo = folds(sub)
    rep[kind] = {m: {"all": metrics(res, [r["id"] for r in sub]),
                     "folds": [metrics(res, [r["id"] for r in sub if fo[r["id"]] == k]) for k in (0, 1)]}
                 for m, res in (("off", off), ("on", on))}
changed = [{"id": i, "label": lab[i], "off": off[i]["verdict"], "on": on[i]["verdict"]} for i in off if off[i]["verdict"] != on[i]["verdict"]]
allids = list(off)
rep["all"] = {"off": metrics(off, allids), "on": metrics(on, allids), "changed": changed}
Path(a.out).write_text(json.dumps(rep, indent=1))
for k in ("doc", "code"):
    for m in ("off", "on"):
        x = rep[k][m]["all"]; print(k, m, {kk: round(v, 3) for kk, v in x.items()})
print("all", {m: {kk: round(v, 3) for kk, v in rep["all"][m].items()} for m in ("off", "on")})
print("changed verdicts:", changed)
