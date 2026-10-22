"""Live check log for the /logs page and the server console.

Keeps the last few hundred checks in memory (nothing on disk). Each event has the time, site,
channel (paste or file), verdict, matched source, the best score per method (MiniLM embedding,
word 3-gram, TF-IDF), whether the fast path skipped MiniLM, and latency. Never the pasted text:
only the first 10 hex chars of its SHA-256 and its length.
"""
import collections
import hashlib
import itertools
import os
import sys
import threading
import time

_EVENTS = collections.deque(maxlen=int(os.environ.get("PG_LIVELOG_SIZE", "500")))
_IDS = itertools.count(1)
_LOCK = threading.Lock()
CONSOLE = os.environ.get("PG_CONSOLE_LOG", "1") != "0"
PATH_LABEL = {"embedding": "MiniLM ran", "cheap_block": "skipped MiniLM (cheap check blocked)",
              "cheap_clear": "skipped MiniLM (no overlap)", "short": "too short to match"}


def _best(matches, method):
    vals = [m["similarity"] for m in matches if m.get("method", "embedding") == method]
    return round(max(vals), 3) if vals else None


def record(channel, site, text, res, ms, path, file_name=None):
    top = res.get("semantic_match") or {}
    matches = res.get("matches") or []
    ev = {"time": time.strftime("%H:%M:%S"), "ts": time.time(), "site": (site or "")[:60], "channel": channel,
          "verdict": res["verdict"], "source": top.get("path"), "kind": top.get("kind"),
          "method": top.get("method"),
          "scores": {"embedding": _best(matches, "embedding"), "ngram": _best(matches, "fingerprint"),
                     "tfidf": _best(matches, "tfidf")},
          "secrets": sorted({f["type"] for f in res.get("findings", [])}),
          "allowlisted": int(res.get("allowlisted") or 0),
          "path": path, "minilm_skipped": path in ("cheap_block", "cheap_clear", "short"),
          "ms": ms, "chars": len(text), "hash": hashlib.sha256(text.encode()).hexdigest()[:10],
          "file": file_name}
    with _LOCK:
        ev["id"] = next(_IDS)
        _EVENTS.append(ev)
    if CONSOLE:
        print(line(ev), file=sys.stdout, flush=True)
    return ev


def since(after=0, limit=200):
    with _LOCK:
        return [e for e in _EVENTS if e["id"] > after][-limit:]


def _f(x):
    return "  -  " if x is None else f"{x:.2f}"


def line(ev):
    """One readable console line per check, no pasted text."""
    s = ev["scores"]
    src = ev["source"] or ("secret: " + ",".join(ev["secrets"]) if ev["secrets"] else "-")
    extra = f"  allowlisted: {ev['allowlisted']}" if ev.get("allowlisted") else ""
    return (f"[{ev['time']}] {ev['verdict'].upper():6} {ev['channel']:5} {ev['site'][:18]:18} "
            f"emb {_f(s['embedding'])} 3gram {_f(s['ngram'])} tfidf {_f(s['tfidf'])} "
            f"{'fast-path' if ev['minilm_skipped'] else 'MiniLM   '} {ev['ms']:4d} ms  "
            f"#{ev['hash']} {ev['chars']} chars  -> {src}{extra}")
