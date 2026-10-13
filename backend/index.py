"""Vector index over the company's code: sqlite-vec, FAISS-free numpy fallback.

CLI:  python index.py build /path/to/repo [--db pg_index.db]
      python index.py query "some code" [--db pg_index.db]
"""
import argparse
import os
import sqlite3
import sys
from pathlib import Path

import numpy as np

import embedder
from chunking import CODE_EXT, SKIP_DIRS, normalise, windows

DB_PATH = os.environ.get("PG_INDEX_DB", str(Path(__file__).with_name("pg_index.db")))

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


def iter_files(repo: Path):
    for p in repo.rglob("*"):
        if p.is_file() and p.suffix in CODE_EXT and not (set(p.parts) & SKIP_DIRS):
            if p.stat().st_size < 500_000:
                yield p


def build_index(repo_path: str, db_path: str = DB_PATH) -> int:
    repo = Path(repo_path).resolve()
    if os.path.exists(db_path):
        os.replace(db_path, db_path + ".prev")  # keep the previous index, never delete
    con = _connect(db_path)
    d = embedder.dim()
    con.execute("CREATE TABLE chunks(id INTEGER PRIMARY KEY, path TEXT, start_line INT, end_line INT, text TEXT, emb BLOB)")
    if HAVE_VEC:
        con.execute(f"CREATE VIRTUAL TABLE vec_chunks USING vec0(embedding float[{d}] distance_metric=cosine)")
    con.execute("CREATE TABLE meta(k TEXT PRIMARY KEY, v TEXT)")
    rows = []
    for f in iter_files(repo):
        text = f.read_text(errors="ignore")
        for s, e, chunk in windows(text):
            rows.append((str(f.relative_to(repo)), s, e, chunk))
    B = 64
    for i in range(0, len(rows), B):
        batch = rows[i:i + B]
        vecs = embedder.embed([normalise(r[3]) for r in batch])
        for r, v in zip(batch, vecs):
            cur = con.execute("INSERT INTO chunks(path,start_line,end_line,text,emb) VALUES(?,?,?,?,?)",
                              (*r, v.tobytes()))
            if HAVE_VEC:
                con.execute("INSERT INTO vec_chunks(rowid, embedding) VALUES(?,?)", (cur.lastrowid, v.tobytes()))
        print(f"indexed {min(i + B, len(rows))}/{len(rows)} chunks", file=sys.stderr)
    con.executemany("INSERT INTO meta VALUES(?,?)", [("repo", str(repo)), ("model", embedder.MODEL_NAME),
                                                    ("chunks", str(len(rows)))])
    con.commit()
    con.close()
    return len(rows)


class Index:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.con = _connect(db_path) if os.path.exists(db_path) else None
        self._mat = None

    def stats(self) -> dict:
        if not self.con:
            return {"built": False}
        meta = dict(self.con.execute("SELECT k, v FROM meta").fetchall())
        return {"built": True, "backend": "sqlite-vec" if HAVE_VEC else "numpy", **meta}

    def query(self, vec: np.ndarray, k: int = 5) -> list[dict]:
        if not self.con:
            return []
        if HAVE_VEC:
            res = self.con.execute(
                "SELECT c.path, c.start_line, c.end_line, v.distance FROM vec_chunks v JOIN chunks c ON c.id = v.rowid "
                "WHERE v.embedding MATCH ? AND k = ? ORDER BY v.distance", (vec.astype(np.float32).tobytes(), k)).fetchall()
            return [{"path": p, "lines": [s, e], "similarity": round(1 - dist, 4)} for p, s, e, dist in res]
        if self._mat is None:
            data = self.con.execute("SELECT path, start_line, end_line, emb FROM chunks").fetchall()
            self._meta = [(p, s, e) for p, s, e, _ in data]
            self._mat = np.stack([np.frombuffer(b, dtype=np.float32) for *_, b in data])
        sims = self._mat @ vec
        top = np.argsort(-sims)[:k]
        return [{"path": self._meta[i][0], "lines": list(self._meta[i][1:]), "similarity": round(float(sims[i]), 4)}
                for i in top]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build"); b.add_argument("repo"); b.add_argument("--db", default=DB_PATH)
    q = sub.add_parser("query"); q.add_argument("text"); q.add_argument("--db", default=DB_PATH)
    a = ap.parse_args()
    if a.cmd == "build":
        print(f"{build_index(a.repo, a.db)} chunks indexed into {a.db}")
    else:
        for hit in Index(a.db).query(embedder.embed([normalise(a.text)])[0]):
            print(hit)
