"""Evaluate Paste Guard: semantic matching vs a regex/keyword baseline.

Loads eval/data/*.jsonl (fields: id, text, label positive|negative, source_doc,
transform), runs every sample through the real backend logic and real index,
and writes eval/results.md plus eval/results.png.

  python eval/run_eval.py            # uses the thresholds in paste-guard.toml
  python eval/run_eval.py --tune     # also sweeps thresholds and prints suggestions
"""
import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "eval"))
import app  # noqa: E402
import secrets_scan  # noqa: E402

from baseline import regex_flag  # noqa: E402


def kind_of(path: Path) -> str:
    return "code" if path.name.startswith("code") else "doc"


def best_sim(text: str, kind: str) -> tuple[float, str | None, float, int]:
    """Best embedding similarity, its source, best 3-gram containment, and the highest verdict level
    (0 none, 1 nudge, 2 coach, 3 block) the deployed hybrid logic reaches for this kind."""
    best, src, fp, lvl, lvl_src = 0.0, None, 0.0, 0, None
    for w in app.semantic(text):
        for h in w["hits"]:
            if h["kind"] != kind:
                continue
            if h.get("method") == "fingerprint":
                fp = max(fp, h["similarity"])
            elif h["similarity"] > best:
                best, src = h["similarity"], h["source"]
            r = app.RANK[app.level(h)]
            if r > lvl:
                lvl, lvl_src = r, h["source"]
    return best, lvl_src or src, fp, lvl


def prf(rows, pred):
    tp = sum(1 for r in rows if r["label"] == "positive" and pred(r))
    fn = sum(1 for r in rows if r["label"] == "positive" and not pred(r))
    fp = sum(1 for r in rows if r["label"] == "negative" and pred(r))
    tn = sum(1 for r in rows if r["label"] == "negative" and not pred(r))
    p = tp / (tp + fp) if tp + fp else 0.0
    rc = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * p * rc / (p + rc) if p + rc else 0.0
    fpr = fp / (fp + tn) if fp + tn else 0.0
    return {"n": len(rows), "tp": tp, "fp": fp, "fn": fn, "tn": tn, "precision": p, "recall": rc, "f1": f1, "fpr": fpr}


def sweep(rows, max_fpr=0.05):
    """Best-F1 threshold with false positive rate at or under max_fpr."""
    best = None
    for t in [x / 100 for x in range(40, 96)]:
        m = prf(rows, lambda r: r["sim"] >= t)
        if m["fpr"] <= max_fpr and (best is None or m["f1"] > best[1]["f1"]):
            best = (t, m)
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tune", action="store_true")
    a = ap.parse_args()
    rows = []
    for f in sorted((ROOT / "eval" / "data").glob("*.jsonl")):
        k = kind_of(f)
        for line in f.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                r["kind"] = k
                rows.append(r)
    print(f"{len(rows)} samples", file=sys.stderr)
    for i, r in enumerate(rows):
        r["sim"], r["hit_src"], r["fp"], r["level"] = best_sim(r["text"], r["kind"])
        r["regex"] = regex_flag(r["text"])
        if i % 50 == 0:
            print(f"  {i}/{len(rows)}", file=sys.stderr)

    T = app.THRESHOLDS
    sem = lambda r: r["level"] >= 2  # noqa: E731  (coach or block is an actionable warning)
    sem_nudge = lambda r: r["level"] >= 1  # noqa: E731
    sem_emb = lambda r: r["sim"] >= T[r["kind"]]["coach"]  # noqa: E731  (embedding only, for comparison)
    sem_block = lambda r: r["level"] >= 3  # noqa: E731
    rgx = lambda r: r["regex"]  # noqa: E731

    out = ["# Paste Guard evaluation results", "",
           f"Model: `{app.embedder.MODEL_NAME}`. Index: {app.INDEX.stats().get('doc_chunks')} document passages, "
           f"{app.INDEX.stats().get('code_chunks')} code chunks. Samples: {len(rows)}.", "",
           "Paste Guard hybrid = the deployed decision logic: embedding cosine bands OR word 3-gram containment bands, "
           "counted at the **coach** level (an actionable warning) unless noted. The model is pretrained and used zero-shot; "
           "nothing is trained. Thresholds below were picked from this same set, so these are in-sample numbers; "
           "held-out numbers (thresholds tuned on other documents) are in `eval/benchmarks.md`. Regex = secrets rules plus CONFIDENTIAL-style markers "
           "plus a sensitive business keyword dictionary.", "",
           "Embedding bands: " + "; ".join(f"{k}: nudge {v['nudge']}, coach {v['coach']}, block {v['block']}"
                                         for k, v in T.items()) + ". Fingerprint bands: " + "; ".join(
               f"{k}: coach {app.FINGERPRINT[k]['coach']}, block {app.FINGERPRINT[k]['block']}" for k in ("doc", "code")), "",
           "## Per kind", "", "| Kind | Method | N | Precision | Recall | F1 | FPR |", "|---|---|---|---|---|---|---|"]
    chart = {}
    for k in ("doc", "code"):
        sub = [r for r in rows if r["kind"] == k]
        if not sub:
            continue
        for name, fn in (("Paste Guard hybrid (coach)", sem), ("Paste Guard hybrid (nudge)", sem_nudge),
                         ("Paste Guard hybrid (block)", sem_block), ("Embedding only (coach)", sem_emb), ("Regex baseline", rgx)):
            m = prf(sub, fn)
            chart[(k, name)] = m
            out.append(f"| {k} | {name} | {m['n']} | {m['precision']:.2f} | {m['recall']:.2f} | {m['f1']:.2f} | {m['fpr']:.2f} |")

    out += ["", "## Recall per transform (positives) and FPR per negative type", "",
            "| Kind | Transform | Label | N | Paste Guard | Regex | Mean embedding similarity |", "|---|---|---|---|---|---|---|"]
    groups = defaultdict(list)
    for r in rows:
        groups[(r["kind"], r["transform"], r["label"])].append(r)
    per_tf = {}
    for (k, tf, lab), g in sorted(groups.items()):
        s = sum(map(sem, g)) / len(g)
        x = sum(map(rgx, g)) / len(g)
        per_tf[(k, tf, lab)] = (s, x)
        what = "detected" if lab == "positive" else "false alarms"
        out.append(f"| {k} | {tf} | {lab} ({what}) | {len(g)} | {s:.2f} | {x:.2f} | {sum(r['sim'] for r in g) / len(g):.3f} |")

    src_ok = [r for r in rows if r["label"] == "positive" and sem(r) and r.get("source_doc")]
    if src_ok:
        acc = sum(1 for r in src_ok if r["hit_src"] and (r["hit_src"].endswith(r["source_doc"]) or r["source_doc"].endswith(r["hit_src"]))) / len(src_ok)
        out += ["", f"Source attribution: for {len(src_ok)} detected positives, the top match pointed at the right "
                f"source file {acc:.0%} of the time."]

    if a.tune:
        out += ["", "## Threshold sweep (best F1 with FPR at or under 5%)", ""]
        for k in ("doc", "code"):
            sub = [r for r in rows if r["kind"] == k]
            b = sweep(sub)
            if b:
                out.append(f"- {k}: threshold {b[0]:.2f} gives precision {b[1]['precision']:.2f}, recall "
                           f"{b[1]['recall']:.2f}, F1 {b[1]['f1']:.2f}, FPR {b[1]['fpr']:.2f}")
    out += ["", "![results](results.png)", ""]
    (ROOT / "eval" / "results.md").write_text("\n".join(out))
    (ROOT / "eval" / "scores.jsonl").write_text("\n".join(json.dumps(
        {"id": r["id"], "kind": r["kind"], "label": r["label"], "transform": r["transform"],
         "sim": r["sim"], "fp": r["fp"], "level": r["level"], "regex": r["regex"]}) for r in rows) + "\n")
    _chart(per_tf)
    print("\n".join(out))


def _chart(per_tf):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    keys = sorted(per_tf)
    labels = [f"{k}:{tf}" + ("" if lab == "positive" else " (neg, FPR)") for k, tf, lab in keys]
    s = [per_tf[x][0] for x in keys]
    g = [per_tf[x][1] for x in keys]
    fig, ax = plt.subplots(figsize=(10, 0.38 * len(keys) + 1.5))
    y = range(len(keys))
    ax.barh([i + 0.2 for i in y], s, height=0.4, label="Paste Guard hybrid (coach)", color="#1f6feb")
    ax.barh([i - 0.2 for i in y], g, height=0.4, label="Regex and keyword baseline", color="#9aa4b2")
    ax.set_yticks(list(y)); ax.set_yticklabels(labels, fontsize=8); ax.invert_yaxis()
    ax.set_xlim(0, 1); ax.set_xlabel("Detection rate (positives) or false alarm rate (negatives)")
    ax.set_title("Paste Guard vs regex DLP baseline, by transform"); ax.legend(loc="lower right", fontsize=8)
    fig.tight_layout(); fig.savefig(ROOT / "eval" / "results.png", dpi=130)


if __name__ == "__main__":
    main()
