"""Verdict log for the admin page. Never stores paste or file content:
only a SHA-256 of the text, its length, the verdict and the matched source name."""
import hashlib
import os
import sqlite3
import threading
import time


class Audit:
    def __init__(self, path: str, keep_days: int = 30):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.con = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.Lock()
        self.keep = keep_days * 86400
        self.con.execute("CREATE TABLE IF NOT EXISTS verdicts(id INTEGER PRIMARY KEY, ts REAL, channel TEXT, site TEXT, "
                         "sha256 TEXT, chars INT, verdict TEXT, match_kind TEXT, match_source TEXT, similarity REAL, "
                         "findings TEXT, ms INT)")
        self.con.commit()

    def record(self, channel, site, text, res, ms):
        top = res.get("semantic_match") or {}
        row = (time.time(), channel, (site or "")[:80], hashlib.sha256(text.encode()).hexdigest(), len(text),
               res["verdict"], top.get("kind"), top.get("source"), top.get("similarity"),
               ",".join(sorted({f["type"] for f in res.get("findings", [])})), ms)
        with self.lock:
            self.con.execute("INSERT INTO verdicts(ts,channel,site,sha256,chars,verdict,match_kind,match_source,"
                             "similarity,findings,ms) VALUES(?,?,?,?,?,?,?,?,?,?,?)", row)
            self.con.execute("DELETE FROM verdicts WHERE ts < ?", (time.time() - self.keep,))  # retention only
            self.con.commit()

    def recent(self, n=50):
        with self.lock:
            cur = self.con.execute("SELECT ts,channel,site,sha256,chars,verdict,match_kind,match_source,similarity,"
                                   "findings,ms FROM verdicts ORDER BY id DESC LIMIT ?", (n,))
            cols = [c[0] for c in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]

    def counts(self, since_s=7 * 86400):
        with self.lock:
            return dict(self.con.execute("SELECT verdict, COUNT(*) FROM verdicts WHERE ts >= ? GROUP BY verdict",
                                         (time.time() - since_s,)).fetchall())
