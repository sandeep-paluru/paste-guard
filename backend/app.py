"""Paste Guard backend. Run: uvicorn app:app --host 127.0.0.1 --port 8765

Combines the secrets scanner with semantic similarity against the indexed
company codebase and returns allow / nudge / coach / block.
"""
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import embedder
import secrets_scan
from chunking import normalise, windows
from index import Index

# Similarity thresholds (cosine). Tuned on the demo repo; see eval/.
T_NUDGE = float(os.environ.get("PG_T_NUDGE", "0.70"))
T_COACH = float(os.environ.get("PG_T_COACH", "0.80"))
T_BLOCK = float(os.environ.get("PG_T_BLOCK", "0.90"))
HARD_SECRETS = {"private_key", "aws_access_key", "github_token", "openai_key", "slack_token"}

app = FastAPI(title="Paste Guard")
_extra = [o for o in os.environ.get("PG_CORS_ORIGINS", "").split(",") if o]
app.add_middleware(CORSMiddleware, allow_origin_regex=r"chrome-extension://.*", allow_origins=_extra,
                   allow_methods=["GET", "POST"], allow_headers=["*"])
INDEX = Index()


class CheckIn(BaseModel):
    text: str
    source: str | None = None


@app.get("/health")
def health():
    return {"status": "ok", "model": embedder.MODEL_NAME, "index": INDEX.stats(),
            "thresholds": {"nudge": T_NUDGE, "coach": T_COACH, "block": T_BLOCK}}


def semantic(text: str):
    """Embed paste windows, return best match overall and per-window scores."""
    wins = list(windows(text, size=30, step=15, min_chars=40)) or [(1, max(1, text.count("\n") + 1), text)]
    vecs = embedder.embed([normalise(w[2]) for w in wins])
    best, per_window = None, []
    for (s, e, _), v in zip(wins, vecs):
        hits = INDEX.query(v, k=3)
        top = hits[0] if hits else None
        per_window.append({"lines": [s, e], "top": top})
        if top and (best is None or top["similarity"] > best["similarity"]):
            best = {**top, "paste_lines": [s, e], "neighbours": hits}
    return best, per_window


def redact_code(text: str, per_window, threshold: float) -> str:
    lines = text.splitlines()
    hit = [False] * len(lines)
    for w in per_window:
        if w["top"] and w["top"]["similarity"] >= threshold:
            for i in range(w["lines"][0] - 1, w["lines"][1]):
                hit[i] = True
    out, i = [], 0
    while i < len(lines):
        if hit[i]:
            j = i
            while j < len(lines) and hit[j]:
                j += 1
            out.append(f"[REDACTED:company_code {j - i} lines]")
            i = j
        else:
            out.append(lines[i]); i += 1
    return "\n".join(out)


@app.post("/check")
def check(req: CheckIn):
    findings = secrets_scan.scan(req.text)
    types = {f["type"] for f in findings}
    match, per_window = semantic(req.text) if len(req.text.strip()) >= 20 else (None, [])
    sim = match["similarity"] if match else 0.0

    if types & HARD_SECRETS:
        verdict, msg = "block", "This paste contains a live credential."
    elif sim >= T_BLOCK:
        verdict, msg = "block", f"This closely matches company code ({match['path']})."
    elif sim >= T_COACH or findings:
        verdict = "coach"
        msg = (f"This looks like company code ({match['path']}). Share a minimal, generic version instead."
               if sim >= T_COACH else "This paste may contain a secret. Consider redacting it.")
    elif sim >= T_NUDGE:
        verdict, msg = "nudge", f"Parts of this resemble company code ({match['path']}). Double check before sending."
    else:
        verdict, msg = "allow", "No issues found."

    redacted = secrets_scan.redact(req.text, findings)
    if sim >= T_COACH:
        redacted = redact_code(redacted, per_window, T_COACH)
    return {"verdict": verdict, "message": msg, "findings": findings,
            "semantic_match": match, "redacted": redacted}
