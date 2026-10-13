"""Score every eval sample with one matching method, in its own process.

  python eval/bench_score.py --method minilm [--chunking full|long_only|bugged_split]

Writes eval/bench/<method>[_<chunking>].json with per-sample best similarity
per kind, the top source, per-check latency, index build time and peak RSS.
Matching mirrors the backend: the paste is cut into the same windows as
backend/app.py (paragraph windows, 30-line windows, whole paste) and the best
score against any indexed chunk of the sample's kind is kept. Embedding
methods use exact cosine (same result as the sqlite-vec index).
"""
import argparse, hashlib, json, os, re, resource, sys, time
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import chunking  # noqa: E402
from chunking import normalise  # noqa: E402

MODELS = {
    "minilm": "sentence-transformers/all-MiniLM-L6-v2",
    "bge-small": "BAAI/bge-small-en-v1.5",
    "bge-base": "BAAI/bge-base-en-v1.5",
    "jina-code": "jinaai/jina-embeddings-v2-base-code",
    "nomic": "nomic-ai/nomic-embed-text-v1.5",
    "bge-large": "BAAI/bge-large-en-v1.5",
    "mxbai-large": "mixedbread-ai/mxbai-embed-large-v1",
    "gte-large": "thenlper/gte-large",
    "arctic-l": "snowflake/snowflake-arctic-embed-l",
    "mpnet-para": "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
}
PREFIX = {"nomic": "search_query: "}  # symmetric use: same prefix on both sides
CACHE = os.path.expanduser("~/.cache/paste-guard/models")


def doc_chunks_bugged(text, target=160, max_words=200, min_words=120, overlap=30):
    """The pre-06a35b3 splitter: long paragraphs were cut with overlap AND packed with overlap."""
    src = Path(chunking.__file__).read_text()
    ns = {}
    exec(compile(src.replace("w = w[target:]", "w = w[target - overlap:]"), "bugged", "exec"), ns)
    return ns["doc_chunks"](text, target, max_words, min_words, overlap)


def corpus(chunk_mode):
    cfg_docs, cfg_code = ROOT / "demo" / "company-docs", ROOT / "demo" / "company-repo"
    rows = []
    for f in sorted(cfg_code.rglob("*")):
        if f.is_file() and f.suffix in chunking.CODE_EXT and not (set(f.parts) & chunking.SKIP_DIRS):
            for s, e, c in chunking.windows(f.read_text(errors="ignore")):
                rows.append(("code", str(f.relative_to(cfg_code)), c))
    for f in sorted(cfg_docs.iterdir()):
        if f.suffix.lower() not in chunking.DOC_EXT:
            continue
        t = chunking.extract_text(f, f.suffix)
        if chunk_mode == "long_only":
            it = chunking.doc_chunks(t)
        elif chunk_mode == "bugged_split":
            it = list(doc_chunks_bugged(t)) + list(doc_chunks_bugged(t, 60, 80, 40, 20))
        else:
            it = chunking.doc_passages(t)
        for s, e, c in it:
            rows.append(("doc", f.name, c))
    return rows


def windows_of(text):
    """Same windows as backend/app.py semantic()."""
    spans = list(dict.fromkeys(chunking.prose_spans(text) + chunking.line_spans(text)))
    if len(text.split()) <= 400:
        spans.append((0, len(text)))
    spans = list(dict.fromkeys(spans))[:48] or [(0, len(text))]
    return [text[s:e] for s, e in spans]


from chunking import shingles  # noqa: E402  (same fingerprint as the backend)


class Embed:
    def __init__(self, key):
        from fastembed import TextEmbedding
        self.key, self.m = key, TextEmbedding(model_name=MODELS[key], cache_dir=CACHE, threads=2)
        self.p = PREFIX.get(key, "")

    def enc(self, texts):
        v = np.array(list(self.m.embed([self.p + normalise(t) for t in texts], batch_size=16)), dtype=np.float32)
        return v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-9)

    def fit(self, rows):
        self.kinds = np.array([r[0] for r in rows]); self.src = [r[1] for r in rows]
        self.M = self.enc([r[2] for r in rows])

    def score(self, wins):
        return self.enc(wins) @ self.M.T


class Tfidf:
    def fit(self, rows):
        from sklearn.feature_extraction.text import TfidfVectorizer
        self.kinds = np.array([r[0] for r in rows]); self.src = [r[1] for r in rows]
        self.v = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, token_pattern=r"\w+", lowercase=True)
        self.M = self.v.fit_transform([r[2] for r in rows])

    def score(self, wins):
        return (self.v.transform(wins) @ self.M.T).toarray()


class Ngram:
    """Word 3-shingle containment: share of the window's shingles found in a chunk."""
    def fit(self, rows):
        self.kinds = np.array([r[0] for r in rows]); self.src = [r[1] for r in rows]
        self.S = [shingles(r[2]) for r in rows]

    def score(self, wins):
        out = np.zeros((len(wins), len(self.S)), dtype=np.float32)
        for i, w in enumerate(wins):
            a = shingles(w)
            if len(a) >= 8:  # same minimum as [fingerprint] min_shingles
                for j, b in enumerate(self.S):
                    out[i, j] = len(a & b) / len(a)
        return out


class MinHash:
    """128-permutation MinHash over word 3-shingles, Jaccard estimate."""
    P = (1 << 61) - 1

    def __init__(self):
        rng = np.random.default_rng(7)
        self.a = rng.integers(1, self.P, 128, dtype=np.uint64); self.b = rng.integers(0, self.P, 128, dtype=np.uint64)

    def sig(self, t):
        s = np.array([x % self.P for x in shingles(t)] or [0], dtype=np.uint64)
        return ((np.outer(s, self.a) + self.b) % np.uint64(self.P)).min(axis=0)

    def fit(self, rows):
        self.kinds = np.array([r[0] for r in rows]); self.src = [r[1] for r in rows]
        self.M = np.stack([self.sig(r[2]) for r in rows])

    def score(self, wins):
        return np.stack([(self.M == self.sig(w)).mean(axis=1) for w in wins])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--method", required=True)
    ap.add_argument("--chunking", default="full")
    a = ap.parse_args()
    sys.path.insert(0, str(ROOT / "eval"))
    rows = corpus(a.chunking)
    t0 = time.time()
    m = Embed(a.method) if a.method in MODELS else {"tfidf": Tfidf, "ngram": Ngram, "minhash": MinHash}[a.method]()
    load_s = time.time() - t0
    t0 = time.time(); m.fit(rows); build_s = time.time() - t0
    samples = []
    for f in ("doc", "code"):
        for line in (ROOT / "eval" / "data" / f"{f}_pastes.jsonl").read_text().splitlines():
            if line.strip():
                r = json.loads(line); r["kind"] = f; samples.append(r)
    out, lat = [], []
    if isinstance(m, Embed):
        m.score(windows_of("warm up the model once"))
    for r in samples:
        t0 = time.time()
        S = m.score(windows_of(r["text"]))
        lat.append((time.time() - t0) * 1000)
        mask = m.kinds == r["kind"]
        col = S[:, mask].max(axis=0)
        j = int(col.argmax())
        src = [s for s, k in zip(m.src, m.kinds) if k == r["kind"]][j]
        out.append({"id": r["id"], "kind": r["kind"], "label": r["label"], "transform": r["transform"],
                    "source_doc": r.get("source_doc", ""), "sim": float(col.max()), "hit_src": src})
    model_mb = None
    if isinstance(m, Embed):
        d = [p for p in Path(CACHE).glob("*") if MODELS[a.method].split("/")[-1].lower() in p.name.lower()]
        model_mb = sum(f.stat().st_size for p in d for f in p.rglob("*") if f.is_file() and not f.is_symlink()) / 1e6 if d else None
        dims = int(m.M.shape[1])
    else:
        dims = None
    name = a.method + ("" if a.chunking == "full" else "_" + a.chunking)
    res = {"method": a.method, "model": MODELS.get(a.method, a.method), "chunking": a.chunking,
           "chunks": len(rows), "doc_chunks": int(sum(r[0] == "doc" for r in rows)), "dims": dims,
           "load_s": load_s, "build_s": build_s, "lat_ms": lat,
           "peak_rss_mb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, "model_mb": model_mb,
           "samples": out}
    (ROOT / "eval" / "bench" / f"{name}.json").write_text(json.dumps(res))
    print(name, f"build {build_s:.1f}s p50 {np.percentile(lat, 50):.0f}ms rss {res['peak_rss_mb']:.0f}MB")


if __name__ == "__main__":
    main()
