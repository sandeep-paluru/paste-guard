"""Aggregate eval/bench/*.json into eval/benchmarks.md and chart PNGs.

Two ways of scoring every method:
  in-sample : threshold tuned on all samples (best F1 with FPR <= 5%), scored on the same samples.
  held-out  : 2-fold split BY SOURCE DOCUMENT (code: by source file). The threshold is tuned on the
              samples from one half of the documents and applied to the other half, then swapped.
              Negatives are split into the two folds by id. Every index still contains all documents,
              as it would in a real deployment; what is held out is the tuning data.
No model is trained. Embedding models are pretrained and used zero-shot; the only fitted values are
the thresholds (and, for TF-IDF, the vocabulary and IDF weights of the indexed corpus).
"""
import hashlib, json, sys
from collections import defaultdict
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend")); sys.path.insert(0, str(ROOT / "eval"))
from baseline import regex_flag  # noqa: E402

B = ROOT / "eval" / "bench"
GRID = [x / 100 for x in range(5, 100)]
LABEL = {"minilm": "all-MiniLM-L6-v2", "bge-small": "bge-small-en-v1.5", "bge-base": "bge-base-en-v1.5",
         "jina-code": "jina-embeddings-v2-base-code", "nomic": "nomic-embed-text-v1.5", "tfidf": "TF-IDF cosine (1-2 grams)",
         "ngram": "Word 3-gram containment", "minhash": "MinHash Jaccard (128 perms)", "regex": "Regex and keyword DLP",
         "hybrid": "Hybrid: MiniLM OR 3-gram containment", "hybrid_tfidf": "Hybrid: MiniLM OR TF-IDF",
         "minilm_long_only": "MiniLM, 120-200 word chunks only (v0.3 before short passages)",
         "minilm_bugged_split": "MiniLM, pre-fix splitter (duplicated overlap)"}


def prf(lab, pred):
    lab, pred = np.asarray(lab), np.asarray(pred)
    tp = int((lab & pred).sum()); fp = int((~lab & pred).sum()); fn = int((lab & ~pred).sum()); tn = int((~lab & ~pred).sum())
    p = tp / (tp + fp) if tp + fp else 0.0; r = tp / (tp + fn) if tp + fn else 0.0
    return {"precision": p, "recall": r, "f1": 2 * p * r / (p + r) if p + r else 0.0, "fpr": fp / (fp + tn) if fp + tn else 0.0,
            "tp": tp, "fp": fp, "fn": fn, "tn": tn}


def tune1(lab, sim, max_fpr=0.05):
    best = (None, {"f1": -1})
    for t in GRID:
        m = prf(lab, sim >= t)
        if m["fpr"] <= max_fpr and m["f1"] > best[1]["f1"]:
            best = (t, m)
    return best[0] if best[0] is not None else 1.01


def tune2(lab, a, b, max_fpr=0.05):
    best = ((1.01, 1.01), -1)
    for t1 in GRID[30:]:
        for t2 in GRID:
            m = prf(lab, (a >= t1) | (b >= t2))
            if m["fpr"] <= max_fpr and m["f1"] > best[1]:
                best = ((t1, t2), m["f1"])
    return best[0]


def folds(samples):
    """Greedy balanced 2-way split of positive sources; negatives by id hash."""
    out = {}
    for kind in ("doc", "code"):
        cnt = defaultdict(int)
        for s in samples:
            if s["kind"] == kind and s["label"] == "positive":
                cnt[s["source_doc"]] += 1
        size, assign = [0, 0], {}
        for src, n in sorted(cnt.items(), key=lambda x: (-x[1], x[0])):
            f = 0 if size[0] <= size[1] else 1
            assign[src] = f; size[f] += n
        for s in samples:
            if s["kind"] == kind:
                out[s["id"]] = assign[s["source_doc"]] if s["label"] == "positive" else int(hashlib.md5(s["id"].encode()).hexdigest(), 16) % 2
    return out


def evaluate(samples, scorer, tuner):
    """Return per-kind in-sample and held-out metrics plus held-out per-sample predictions."""
    fold = folds(samples)
    res = {}
    for kind in ("doc", "code"):
        sub = [s for s in samples if s["kind"] == kind]
        lab = np.array([s["label"] == "positive" for s in sub])
        f = np.array([fold[s["id"]] for s in sub])
        t_all = tuner(lab, sub)
        ins = prf(lab, scorer(sub, t_all))
        held = np.zeros(len(sub), bool); ts = []
        for k in (0, 1):
            tr, te = f != k, f == k
            t = tuner(lab[tr], [s for s, m in zip(sub, tr) if m])
            ts.append(t)
            held[te] = scorer([s for s, m in zip(sub, te) if m], t)
        res[kind] = {"t_all": t_all, "t_folds": ts, "in": ins, "held": prf(lab, held),
                     "held_pred": {s["id"]: bool(p) for s, p in zip(sub, held)},
                     "in_pred": {s["id"]: bool(p) for s, p in zip(sub, scorer(sub, t_all))}}
    return res


def model_mb(name):
    import subprocess, os
    cache = Path(os.path.expanduser("~/.cache/paste-guard/models"))
    d = [p for p in cache.glob("*") if name.split("/")[-1].lower() in p.name.lower()]
    if not d:
        return 0
    return int(subprocess.run(["du", "-sbL", *map(str, d)], capture_output=True, text=True).stdout.split()[0]) / 1e6


def main():
    runs = {p.stem: json.loads(p.read_text()) for p in sorted(B.glob("*.json")) if not p.stem.endswith("_latency")}
    base = runs["minilm"]["samples"]
    by_id = {r["id"]: r for r in base}
    texts = {}
    for f in ("doc", "code"):
        for line in (ROOT / "eval" / "data" / f"{f}_pastes.jsonl").read_text().splitlines():
            if line.strip():
                r = json.loads(line); texts[r["id"]] = r["text"]
    sim = {name: {s["id"]: s["sim"] for s in run["samples"]} for name, run in runs.items()}
    hitsrc = {name: {s["id"]: s["hit_src"] for s in run["samples"]} for name, run in runs.items()}

    def single(name):
        sc = lambda sub, t: np.array([sim[name][s["id"]] >= t for s in sub])  # noqa: E731
        tu = lambda lab, sub: tune1(lab, np.array([sim[name][s["id"]] for s in sub]))  # noqa: E731
        return sc, tu

    results = {}
    order = ["minilm", "bge-small", "bge-base", "jina-code", "nomic", "tfidf", "ngram", "minhash"]
    order = [o for o in order if o in runs]
    for name in order + [n for n in runs if n not in order]:
        results[name] = evaluate(base, *single(name))
    rx = {i: regex_flag(texts[i]) for i in by_id}
    results["regex"] = evaluate(base, lambda sub, t: np.array([rx[s["id"]] for s in sub]), lambda lab, sub: 0)
    hy = None
    for key, (e, f) in {"hybrid": ("minilm", "ngram"), "hybrid_tfidf": ("minilm", "tfidf")}.items():
        if f not in runs:
            continue

        def hsc(sub, t, e=e, f=f):
            return np.array([(sim[e][s["id"]] >= t[0]) | (sim[f][s["id"]] >= t[1]) for s in sub])

        def htu(lab, sub, e=e, f=f):
            return tune2(lab, np.array([sim[e][s["id"]] for s in sub]), np.array([sim[f][s["id"]] for s in sub]))
        results[key] = evaluate(base, hsc, htu)
        hy = hy or results[key]
    md = ["# Paste Guard benchmarks", "",
          "Everything on this page was produced by `eval/bench_all.sh` (scoring in `eval/bench_score.py`, "
          "report in `eval/bench_report.py`) on CPU, 2 ONNX threads per model, on the same 472 samples as "
          "`eval/results.md` (356 document pastes over 18 Calloway Metrics documents, 116 code pastes over one repository).", "",
          "**No model was trained or fine-tuned.** Every embedding model is a public pretrained checkpoint used zero-shot "
          "through fastembed (ONNX). The only values fitted to our data are similarity thresholds (and, for TF-IDF, the IDF "
          "weights of the indexed corpus).", "",
          "**In-sample** = threshold tuned and scored on all samples (best F1 with false positive rate at most 5%). "
          "**Held-out** = 2-fold split by source document: thresholds tuned on pastes from 9 documents (code: half the source "
          "files) and scored on pastes from the other 9, then swapped. Negatives are split between folds by id. Held-out is the "
          "honest estimate of how the tuned thresholds carry over to documents they were never tuned on.", "",
          "Charts: `bench_f1.png` (F1 in-sample vs held-out), `bench_transforms.png` (recall by transform), `bench_speed.png` "
          "(accuracy vs latency and RAM). Decisions taken from these numbers are in `docs/OPTIMIZATION_LOG.md`.", ""]

    def row(name, kind):
        r = results[name][kind]
        t = r["t_all"]
        ts = "n/a" if name == "regex" else (f"{t[0]:.2f} / {t[1]:.2f}" if isinstance(t, tuple) else f"{t:.2f}")
        i, h = r["in"], r["held"]
        return (f"| {LABEL.get(name, name)} | {ts} | {i['precision']:.2f} | {i['recall']:.2f} | {i['f1']:.2f} | {i['fpr']:.2f} "
                f"| {h['precision']:.2f} | {h['recall']:.2f} | {h['f1']:.2f} | {h['fpr']:.2f} |")

    names = order + [h for h in ("hybrid", "hybrid_tfidf") if h in results] + ["regex"]
    for kind, title in (("doc", "Documents"), ("code", "Code")):
        md += [f"## {title}: accuracy", "", "| Method | Threshold | P (in) | R (in) | F1 (in) | FPR (in) | P (held-out) | R (held-out) | F1 (held-out) | FPR (held-out) |",
               "|---|---|---|---|---|---|---|---|---|---|"]
        md += [row(n, kind) for n in names] + [""]

    abl = [n for n in ("minilm_long_only", "minilm_bugged_split", "minilm") if n in results]
    if len(abl) > 1:
        md += ["## Chunking ablation (MiniLM, documents)", "",
               "Same model and paste windows, different ways of cutting the documents into indexed passages.", "",
               "| Index | Doc passages | F1 (in) | R (in) | R at fixed 0.63 | F1 (held-out) | R (held-out) |", "|---|---|---|---|---|---|---|"]
        for n in abl:
            r = results[n]["doc"]; sub = [s for s in base if s["kind"] == "doc"]
            fixed = prf(np.array([s["label"] == "positive" for s in sub]), np.array([sim[n][s["id"]] >= 0.63 for s in sub]))
            md.append(f"| {LABEL.get(n, n) if n != 'minilm' else 'MiniLM, long chunks + 60 word passages (current)'} | {runs[n]['doc_chunks']} "
                      f"| {r['in']['f1']:.2f} | {r['in']['recall']:.2f} | {fixed['recall']:.2f} | {r['held']['f1']:.2f} | {r['held']['recall']:.2f} |")
        md.append("")

    # per transform, held-out
    tfs = sorted({(s["kind"], s["transform"], s["label"]) for s in base})
    md += ["## Detection per transform (held-out thresholds)", "",
           "Positives: share detected. Negatives: share falsely flagged.", "",
           "| Kind | Transform | N | " + " | ".join(LABEL.get(n, n) for n in names) + " |",
           "|---|---|---|" + "---|" * len(names)]
    tf_tab = {}
    for k, tf, lab in tfs:
        ids = [s["id"] for s in base if (s["kind"], s["transform"], s["label"]) == (k, tf, lab)]
        vals = [np.mean([results[n][k]["held_pred"][i] for i in ids]) for n in names]
        tf_tab[(k, tf, lab)] = dict(zip(names, vals))
        md.append(f"| {k} | {tf}{'' if lab == 'positive' else ' (negative)'} | {len(ids)} | " + " | ".join(f"{v:.2f}" for v in vals) + " |")

    # attribution
    md += ["", "## Source attribution", "", "For detected document positives (held-out), how often the top hit is the right document.", "",
           "| Method | Correct source |", "|---|---|"]
    for n in order + [h for h in ("hybrid",) if h in results]:
        ids = [s["id"] for s in base if s["kind"] == "doc" and s["label"] == "positive" and results[n]["doc"]["held_pred"][s["id"]]]
        hs = hitsrc["minilm"] if n == "hybrid" else hitsrc[n]
        ok = [hs[i] == by_id[i]["source_doc"] or by_id[i]["source_doc"].endswith(hs[i] or "#") for i in ids]
        md.append(f"| {LABEL.get(n, n)} | {np.mean(ok):.0%} of {len(ids)} |")

    # cost
    md += ["", "## Speed and footprint (this box, CPU)", "",
           "Latency is one full check: cut the paste into windows, embed them, search all indexed chunks. Index build = embedding "
           "all 594 chunks (485 document passages, 109 code chunks). RSS = peak resident memory of the scoring process with "
           "model and index loaded.", "",
           "| Method | Dims | Model on disk | Load | Index build | p50 per check | p95 per check | Peak RSS |", "|---|---|---|---|---|---|---|---|"]
    for n in order:
        r = runs[n]
        md.append(f"| {LABEL.get(n, n)} | {r['dims'] or '-'} | {('%.0f MB' % model_mb(r['model'])) if r['dims'] else '-'} | {r['load_s']:.1f} s "
                  f"| {r['build_s']:.1f} s | {np.percentile(r['lat_ms'], 50):.0f} ms | {np.percentile(r['lat_ms'], 95):.0f} ms | {r['peak_rss_mb']:.0f} MB |")
    vm = ROOT / "eval" / "bench" / "vm_latency.json"
    if vm.exists():
        v = json.loads(vm.read_text())
        md += ["", f"Deployed model on the Techvista VM ({v['host']}, {v['cpus']} vCPU, {v['ram']}): {v['n']} real `/check` calls "
               f"over HTTP on the VM itself (hybrid matching, PG_THREADS=1, VM shared with the existing Techvista services), "
               f"p50 {v['p50']:.0f} ms, p95 {v['p95']:.0f} ms, backend RSS {v['rss_mb']:.0f} MB. The VM is short on memory and "
               "pages part of the process out, which is what drives the p95."]
    bx = ROOT / "eval" / "bench" / "box_latency.json"
    if bx.exists():
        v = json.loads(bx.read_text())
        md += ["", f"Same HTTP test against the backend on this box ({v['cpus']} vCPU): p50 {v['p50']:.0f} ms, p95 {v['p95']:.0f} ms, "
               f"backend RSS {v['rss_mb']:.0f} MB."]
    (ROOT / "eval" / "bench_summary.json").write_text(json.dumps(
        {n: {k: {"t": results[n][k]["t_all"], "in": results[n][k]["in"], "held": results[n][k]["held"], "t_folds": results[n][k]["t_folds"]}
             for k in ("doc", "code")} for n in names}, default=str, indent=1))
    (ROOT / "eval" / "benchmarks.md").write_text("\n".join(md) + "\n")
    charts(results, names, order, runs, tf_tab)
    print("\n".join(md))


def charts(results, names, order, runs, tf_tab):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    out = ROOT / "eval"
    fig, axs = plt.subplots(1, 2, figsize=(12, 4.8))
    for ax, kind in zip(axs, ("doc", "code")):
        y = np.arange(len(names))
        ax.barh(y + 0.2, [results[n][kind]["in"]["f1"] for n in names], 0.4, label="in-sample", color="#9aa4b2")
        ax.barh(y - 0.2, [results[n][kind]["held"]["f1"] for n in names], 0.4, label="held-out (by document)", color="#1f6feb")
        ax.set_yticks(y); ax.set_yticklabels([LABEL.get(n, n) for n in names], fontsize=8); ax.invert_yaxis()
        ax.set_xlim(0, 1); ax.set_title(f"F1, {kind} pastes"); ax.legend(fontsize=8, loc="lower right")
    fig.tight_layout(); fig.savefig(out / "bench_f1.png", dpi=130); plt.close(fig)

    pos = [k for k in tf_tab if k[0] == "doc" and k[2] == "positive"]
    show = [n for n in ("minilm", "bge-small", "bge-base", "ngram", "hybrid", "regex") if n in names]
    fig, ax = plt.subplots(figsize=(11, 4.8))
    w = 0.8 / len(show)
    for i, n in enumerate(show):
        ax.bar(np.arange(len(pos)) + i * w, [tf_tab[k][n] for k in pos], w, label=LABEL.get(n, n))
    ax.set_xticks(np.arange(len(pos)) + 0.4 - w / 2); ax.set_xticklabels([k[1] for k in pos], rotation=20, fontsize=8)
    ax.set_ylim(0, 1); ax.set_ylabel("Recall (held-out thresholds)"); ax.set_title("Document pastes: recall by transform")
    ax.legend(fontsize=7, ncol=3); fig.tight_layout(); fig.savefig(out / "bench_transforms.png", dpi=130); plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 4.8))
    for n in order:
        x = np.percentile(runs[n]["lat_ms"], 50); y = results[n]["doc"]["held"]["f1"]
        ax.scatter(x, y, s=max(runs[n]["peak_rss_mb"], 60) / 3, alpha=0.6); ax.annotate(LABEL.get(n, n), (x, y), fontsize=7)
    ax.set_xscale("log"); ax.set_xlabel("p50 ms per check (log)"); ax.set_ylabel("Held-out F1, documents")
    ax.set_title("Accuracy vs speed (bubble = peak RAM)"); fig.tight_layout(); fig.savefig(out / "bench_speed.png", dpi=130); plt.close(fig)


if __name__ == "__main__":
    main()
