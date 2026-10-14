"""Vector index over company code AND company documents (sqlite-vec, numpy fallback).

CLI:  python index.py build --code ../demo/company-repo --docs ../demo/company-docs [--db data/index.db]
      python index.py query "some text" [--db data/index.db]

Each chunk stores kind=doc|code and its source path, so verdicts can use
separate thresholds per kind and the overlay can show the matched passage.
"""
import argparse
import os
import sqlite3
import sys
from pathlib import Path

import numpy as np

import embedder
from chunking import CODE_EXT, DOC_EXT, SKIP_DIRS, doc_chunks, doc_passages, extract_text, normalise, shingles, windows

from config import CONFIG

DB_PATH = CONFIG["index"]["db"]

try:
    import sqlite_vec
    HAVE_VEC = True
except ImportError:  # fallback: brute-force cosine in numpy over stored blobs
    HAVE_VEC = False


def _connect(db_path: str) -> sqlite3.Connection:
    con = sqlite3.connect(db_path, check_same_thread=False)
    if HAVE_VEC:
        con.enable_load_extension(True)
        sqlite_vec.load(con)
        con.enable_load_extension(False)
    return con


def iter_files(root: Path, exts):
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.suffix.lower() in exts and not (set(p.parts) & SKIP_DIRS):
            if p.stat().st_size < 5_000_000:
                yield p


def collect(code_dirs=(), doc_dirs=()):
    """Return rows (kind, source, start, end, text)."""
    rows = []
    for d in code_dirs:
        root = Path(d).resolve()
        if not root.is_dir():
            print(f"warning: code folder not found, skipping: {root}", file=sys.stderr)
            continue
        for f in iter_files(root, CODE_EXT):
            for s, e, chunk in windows(f.read_text(errors="ignore")):
                rows.append(("code", f.relative_to(root).as_posix(), s, e, chunk))
    for d in doc_dirs:
        root = Path(d).resolve()
        if not root.is_dir():
            print(f"warning: docs folder not found, skipping: {root}", file=sys.stderr)
            continue
        for f in iter_files(root, DOC_EXT):
            try:
                text = extract_text(f, f.suffix)
            except Exception as ex:  # unreadable file: report and continue
                print(f"skip {f}: {ex}", file=sys.stderr)
                continue
            for s, e, chunk in doc_passages(text):
                rows.append(("doc", f.relative_to(root).as_posix(), s, e, chunk))
    return rows


def build_index(code_dirs=(), doc_dirs=(), db_path: str = DB_PATH) -> int:
    rows = collect(code_dirs, doc_dirs)
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    tmp = db_path + ".building"
    if os.path.exists(tmp):
        os.replace(tmp, tmp + ".stale")
    con = _connect(tmp)
    d = embedder.dim()
    con.execute("CREATE TABLE chunks(id INTEGER PRIMARY KEY, kind TEXT, path TEXT, start_line INT, end_line INT, "
                "text TEXT, emb BLOB)")
    if HAVE_VEC:
        con.execute(f"CREATE VIRTUAL TABLE vec_chunks USING vec0(embedding float[{d}] distance_metric=cosine)")
    con.execute("CREATE TABLE meta(k TEXT PRIMARY KEY, v TEXT)")
    B = 32
    for i in range(0, len(rows), B):
        batch = rows[i:i + B]
        vecs = embedder.embed([normalise(r[4]) for r in batch])
        for r, v in zip(batch, vecs):
            cur = con.execute("INSERT INTO chunks(kind,path,start_line,end_line,text,emb) VALUES(?,?,?,?,?,?)",
                              (*r, v.tobytes()))
            if HAVE_VEC:
                con.execute("INSERT INTO vec_chunks(rowid, embedding) VALUES(?,?)", (cur.lastrowid, v.tobytes()))
        print(f"indexed {min(i + B, len(rows))}/{len(rows)} chunks", file=sys.stderr)
    n_doc = sum(r[0] == "doc" for r in rows)
    con.executemany("INSERT INTO meta VALUES(?,?)", [
        ("code_dirs", ",".join(str(Path(x).name) for x in code_dirs)),
        ("doc_dirs", ",".join(str(Path(x).name) for x in doc_dirs)),
        ("model", embedder.MODEL_NAME), ("chunks", str(len(rows))), ("doc_chunks", str(n_doc)),
        ("code_chunks", str(len(rows) - n_doc))])
    con.execute("INSERT INTO meta VALUES('built_at', datetime('now'))")
    con.commit()
    con.close()
    if os.path.exists(db_path):
        os.replace(db_path, db_path + ".prev")  # keep the previous index as a backup
    os.replace(tmp, db_path)  # atomic swap; a running server reloads it automatically
    return len(rows)


def _hit(kind, path, s, e, text, sim):
    snippet = text if len(text) <= 400 else text[:400].rsplit(" ", 1)[0] + " ..."
    return {"kind": kind, "path": path, "source": path, "lines": [s, e],
            "unit": "paragraphs" if kind == "doc" else "lines",
            "similarity": round(float(sim), 4), "snippet": snippet, "method": "embedding"}


class Index:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._open()

    def _open(self):
        self.mtime = os.path.getmtime(self.db_path) if os.path.exists(self.db_path) else None
        self.con = _connect(self.db_path) if self.mtime else None
        self._mat = None
        self._fp = None
        self._tf = None

    def refresh(self):
        """Reopen the index if it was rebuilt on disk (e.g. by `pasteguard reindex`)."""
        m = os.path.getmtime(self.db_path) if os.path.exists(self.db_path) else None
        if m != self.mtime:
            self._open()

    def stats(self) -> dict:
        if not self.con:
            return {"built": False}
        meta = dict(self.con.execute("SELECT k, v FROM meta").fetchall())
        return {"built": True, "backend": "sqlite-vec" if HAVE_VEC else "numpy", **meta}

    def fingerprint(self, text: str, min_shingles: int = 8) -> list[dict]:
        """Best chunk per kind by word 3-gram containment. Catches verbatim and partial reuse that a
        single sentence embedding blurs out. Sets are built in memory from the index on first use."""
        if not self.con:
            return []
        if self._fp is None:
            rows = self.con.execute("SELECT kind, path, start_line, end_line, text FROM chunks").fetchall()
            self._fp = [(r, shingles(r[4])) for r in rows]
        a = shingles(text)
        if len(a) < min_shingles:
            return []
        best = {}
        for r, b in self._fp:
            c = len(a & b) / len(a)
            if c > 0 and (r[0] not in best or c > best[r[0]][1]):
                best[r[0]] = (r, c)
        out = []
        for r, c in best.values():
            h = _hit(*r, c)
            h["method"] = "fingerprint"
            out.append(h)
        return out

    def tfidf(self, texts: list[str]) -> list[list[dict]]:
        """Best chunk per kind by TF-IDF cosine (word 1-2 grams, sublinear tf), one list per text.
        Vocabulary and IDF weights come from the indexed chunks only; nothing is trained."""
        if not self.con or not texts:
            return [[] for _ in texts]
        if self._tf is None:
            from sklearn.feature_extraction.text import TfidfVectorizer
            rows = self.con.execute("SELECT kind, path, start_line, end_line, text FROM chunks").fetchall()
            v = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, token_pattern=r"\w+", lowercase=True)
            self._tf = (rows, v, v.fit_transform([r[4] for r in rows]), np.array([r[0] for r in rows]))
        rows, v, M, kinds = self._tf
        S = (v.transform(texts) @ M.T).toarray()
        out = []
        for srow in S:
            hits = []
            for kd in ("doc", "code"):
                idx = np.where(kinds == kd)[0]
                if len(idx):
                    j = idx[int(srow[idx].argmax())]
                    if srow[j] > 0:
                        h = _hit(*rows[j], srow[j]); h["method"] = "tfidf"; hits.append(h)
            out.append(hits)
        return out

    def query(self, vec: np.ndarray, k: int = 5, kind: str | None = None) -> list[dict]:
        if not self.con:
            return []
        if HAVE_VEC:
            fetch = k * 4 if kind else k
            res = self.con.execute(
                "SELECT c.kind, c.path, c.start_line, c.end_line, c.text, v.distance FROM vec_chunks v "
                "JOIN chunks c ON c.id = v.rowid WHERE v.embedding MATCH ? AND k = ? ORDER BY v.distance",
                (vec.astype(np.float32).tobytes(), fetch)).fetchall()
            hits = [_hit(kd, p, s, e, t, 1 - dist) for kd, p, s, e, t, dist in res]
        else:
            if self._mat is None:
                data = self.con.execute("SELECT kind, path, start_line, end_line, text, emb FROM chunks").fetchall()
                self._meta = [r[:5] for r in data]
                self._mat = np.stack([np.frombuffer(r[5], dtype=np.float32) for r in data])
            sims = self._mat @ vec
            hits = [_hit(*self._meta[i], float(sims[i])) for i in np.argsort(-sims)[:k * 4]]
        if kind:
            hits = [h for h in hits if h["kind"] == kind]
        return hits[:k]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("repo", nargs="*", help="code directories (positional, kept for compatibility)")
    b.add_argument("--code", action="append", default=[])
    b.add_argument("--docs", action="append", default=[])
    b.add_argument("--db", default=DB_PATH)
    sub.add_parser("reindex", help="rebuild from the folders in paste-guard.toml")
    q = sub.add_parser("query"); q.add_argument("text"); q.add_argument("--db", default=DB_PATH)
    a = ap.parse_args()
    if a.cmd == "reindex":
        n = build_index(CONFIG["index"]["code"], CONFIG["index"]["docs"], DB_PATH)
        print(f"{n} chunks indexed into {DB_PATH}")
    elif a.cmd == "build":
        print(f"{build_index(a.repo + a.code, a.docs, a.db)} chunks indexed into {a.db}")
    else:
        for hit in Index(a.db).query(embedder.embed([normalise(a.text)])[0]):
            print(hit)
