"""'Why this matched': sentence-level evidence for a flagged hit.

For each flagged hit we return up to three (paste sentence, source sentence) pairs, each short enough to show
side by side in the overlay. Three ways to pair them, cheapest first:
  ngram     shared word 3-gram runs (exact or near-exact phrases), marks are the shared phrases
  tfidf     shared content words, for rewrites that keep the vocabulary but not the phrasing
  semantic  best sentence alignment by MiniLM cosine, one batch for every hit, vectors cached
Only called for pastes that were flagged, so benign pastes never pay for any of this.
"""
import os
import re

import numpy as np

import embedder
from chunking import clean, normalise

MAX_CHARS = 240        # per displayed snippet
MAX_PAIRS = 3
MAX_SEM_PASTE = 3      # paste sentences embedded per hit (the longest ones)
MAX_SEM_SOURCE = 4     # source sentences embedded per hit (best word overlap with the paste window)
MAX_HITS = int(os.environ.get("PG_EXPLAIN_HITS", "3"))  # flagged hits explained per paste (0 turns it off)
MAX_SEGMENTS = 14      # per side, bounds the embedding batch
WINDOW_CAP = 20000     # characters of a paste window looked at
MIN_SEMANTIC = 0.5     # lowest sentence cosine worth showing
_SPLIT = re.compile(r"(?<=[.!?])\s+|\s*\n\s*")
_WORD = re.compile(r"\w+")
_VEC_CACHE: dict[str, np.ndarray] = {}


def _tokens(text: str, base: int = 0):
    """(word, start, end) per word, lower-cased and cleaned (homoglyphs, zero-width) like the fingerprint,
    with offsets that index into the original text."""
    cleaned = text if text.isascii() else clean(text)
    if len(cleaned) == len(text):  # nothing was dropped or expanded, offsets map one to one
        return [(m.group().lower(), base + m.start(), base + m.end()) for m in _WORD.finditer(cleaned)]
    out, origin = [], []
    for i, ch in enumerate(text):
        c = clean(ch)
        out.append(c)
        origin.extend([i] * len(c))
    cleaned = "".join(out)
    return [(m.group().lower(), base + origin[m.start()], base + origin[m.end() - 1] + 1)
            for m in _WORD.finditer(cleaned)]


def _segments(text: str, kind: str):
    """(start, end) of sentences (documents) or lines (code), at least a few words long."""
    segs, pos = [], 0
    pieces = [(m.start(), m.end()) for m in _SPLIT.finditer(text)] if kind == "doc" else \
        [(m.start(), m.end()) for m in re.finditer(r"\n", text)]
    bounds = [(pos, None)]
    for s, e in pieces:
        bounds[-1] = (bounds[-1][0], s)
        bounds.append((e, None))
    bounds[-1] = (bounds[-1][0], len(text))
    cut = []
    for s, e in bounds:  # table rows and run-on text have no sentence ends: cap the length of one segment
        while e - s > MAX_CHARS + 60:
            k = text.rfind(" ", s + 60, s + MAX_CHARS)
            k = k if k > 0 else s + MAX_CHARS
            cut.append((s, k))
            s = k
        cut.append((s, e))
    for s, e in cut:
        seg = text[s:e]
        s += len(seg) - len(seg.lstrip())
        e = s + len(seg.strip())
        if len(_WORD.findall(text[s:e])) >= 3 and e - s >= 12:
            segs.append((s, e))
    return segs[:MAX_SEGMENTS]


class _Seg:
    def __init__(self, text, s, e):
        self.s, self.e = s, e
        self.toks = _tokens(text[s:e], s)
        w = [t[0] for t in self.toks]
        self.tri = [tuple(w[i:i + 3]) for i in range(len(w) - 2)]
        self.words = {x for x in w if len(x) >= 5}


def _spans(toks, idx):
    """Merge token indexes into character spans of runs of adjacent words."""
    out = []
    for i in sorted(idx):
        s, e = toks[i][1], toks[i][2]
        if out and i == out[-1][2] + 1:
            out[-1][1], out[-1][2] = e, i
        else:
            out.append([s, e, i])
    return [[s, e] for s, e, _ in out]


def _trim(s, e, marks):
    """Shorten a snippet to MAX_CHARS around its first mark, on word boundaries. marks: absolute spans."""
    if e - s > MAX_CHARS:
        a = max(s, (marks[0][0] - 40) if marks else s)
        b = min(e, a + MAX_CHARS)
        s, e = a, b
    return s, e


def _snippet(text, s, e, marks):
    """-> (span, text, marks relative to the snippet) trimmed to MAX_CHARS, snapped to word boundaries."""
    s0, e0 = _trim(s, e, marks)
    if s0 > s and not text[s0 - 1].isspace():
        m = re.compile(r"\s").search(text, s0, e0)
        s0 = m.end() if m else s0
    if e0 < e and not text[e0].isspace():
        k = text.rfind(" ", s0, e0)
        e0 = k if k > s0 else e0
    rel = [[max(a, s0) - s0, min(b, e0) - s0] for a, b in marks if b > s0 and a < e0]
    return [s0, e0], text[s0:e0], rel


def _lex_pairs(P, S, ptext, stext, hit_kind, mode):
    """Pairs by shared 3-gram runs (mode ngram) or shared content words (mode tfidf)."""
    scored = []
    for a in P:
        best = None
        for b in S:
            if mode == "ngram":
                shared = set(a.tri) & set(b.tri)
                n, denom = len(shared), len(a.tri)
                ok = n >= 2
            else:
                shared = a.words & b.words
                n, denom = len(shared), len(a.words)
                ok = n >= 2 and n / max(denom, 1) >= 0.3
            if ok and (best is None or n > best[0]):
                best = (n, shared, b, denom)
        if best:
            scored.append((best[0] / max(best[3], 1), a, best[2], best[1]))
    scored.sort(key=lambda x: -x[0])
    out = []
    for sc, a, b, shared in scored[:MAX_PAIRS]:
        if mode == "ngram":
            ia = {k for i, t in enumerate(a.tri) if t in shared for k in (i, i + 1, i + 2)}
            ib = {k for i, t in enumerate(b.tri) if t in shared for k in (i, i + 1, i + 2)}
        else:
            ia = {i for i, t in enumerate(a.toks) if t[0] in shared}
            ib = {i for i, t in enumerate(b.toks) if t[0] in shared}
        out.append((min(sc, 1.0), a, b, _spans(a.toks, ia), _spans(b.toks, ib), mode))
    return out


def _vectors(texts):
    """Embed the texts not cached yet in ONE batch; return all vectors in order."""
    todo = [t for t in dict.fromkeys(texts) if t not in _VEC_CACHE]
    if todo:
        if len(_VEC_CACHE) > 4000:
            _VEC_CACHE.clear()
        for t, v in zip(todo, embedder.embed(todo)):
            _VEC_CACHE[t] = v
    return [_VEC_CACHE[t] for t in texts]


def seed(texts: list[str], vecs) -> None:
    """Reuse vectors the matcher already computed (a one sentence window is its own sentence)."""
    if len(_VEC_CACHE) > 4000:
        _VEC_CACHE.clear()
    for t, v in zip(texts, vecs):
        _VEC_CACHE[normalise(t)] = v


def _shortlist(P, S):
    """Few paste and source sentences worth embedding: longest paste sentences, source sentences that share
    the most vocabulary with the paste window (all of them when nothing overlaps)."""
    P = sorted(sorted(P, key=lambda a: -(a.e - a.s))[:MAX_SEM_PASTE], key=lambda a: a.s)
    pw = set().union(*(a.words for a in P)) if P else set()
    S = sorted(S, key=lambda b: -len(b.words & pw))[:MAX_SEM_SOURCE]
    return P, sorted(S, key=lambda b: b.s)


def explain(text: str, hits: list[dict]) -> None:
    """Adds hit['matches'] to every hit that has a level; pops the internal '_text' chunk from all of them."""
    work = []  # (hit, paste window, P, S, ptext, stext, pairs)
    for h in hits:
        h["matches"] = []
        if not h.get("level") or "_text" not in h or len(work) >= MAX_HITS:
            continue
        ps, pe = h["paste_span"]
        pe = min(pe, ps + WINDOW_CAP)
        ptext, stext = text[ps:pe], h["_text"]
        P = [_Seg(ptext, s, e) for s, e in _segments(ptext, h["kind"])]
        S = [_Seg(stext, s, e) for s, e in _segments(stext, h["kind"])]
        pairs = _lex_pairs(P, S, ptext, stext, h["kind"], "ngram")
        if len(pairs) < 2 and h.get("method") == "tfidf":
            pairs += [p for p in _lex_pairs(P, S, ptext, stext, h["kind"], "tfidf")
                      if p[1] not in {q[1] for q in pairs}]
        work.append([h, ps, ptext, stext, P, S, pairs[:MAX_PAIRS]])
    # MiniLM alignment only for the top flagged hit that needs it: each embedded sentence costs real latency
    need = [w for w in work if len(w[6]) < 2 and w[4] and w[5]][:1]
    sem = {}
    for w in need:
        w[4], w[5] = _shortlist(w[4], w[5])
    if need:  # semantic alignment for every hit that still has fewer than two pairs: one embedding batch
        texts = []
        for w in need:
            texts += [normalise(w[2][a.s:a.e]) for a in w[4]] + [normalise(w[3][b.s:b.e]) for b in w[5]]
        vecs = dict(zip(texts, _vectors(texts)))
        for w in need:
            pv = np.stack([vecs[normalise(w[2][a.s:a.e])] for a in w[4]])
            sv = np.stack([vecs[normalise(w[3][b.s:b.e])] for b in w[5]])
            sim = pv @ sv.T
            used = {p[1] for p in w[6]}
            cand = []
            for i, a in enumerate(w[4]):
                j = int(sim[i].argmax())
                if a not in used and sim[i, j] >= MIN_SEMANTIC:
                    cand.append((float(sim[i, j]), a, w[5][j], [], [], "semantic"))
            cand.sort(key=lambda x: -x[0])
            sem[id(w[0])] = cand[:MAX_PAIRS - len(w[6])]
    for h, ps, ptext, stext, P, S, pairs in work:
        out = []
        for sc, a, b, pm, sm, kind in pairs + sem.get(id(h), []):
            pspan, ptxt, prel = _snippet(ptext, a.s, a.e, [[x + 0, y] for x, y in pm])
            sspan, stxt, srel = _snippet(stext, b.s, b.e, sm)
            out.append({"paste_span": [pspan[0] + ps, pspan[1] + ps], "paste_text": ptxt, "paste_marks": prel,
                        "source_doc": h["path"], "source_text": stxt, "source_span": sspan, "source_marks": srel,
                        "kind": kind, "score": round(sc, 3)})
        h["matches"] = out[:MAX_PAIRS]
    for h in hits:
        h.pop("_text", None)
