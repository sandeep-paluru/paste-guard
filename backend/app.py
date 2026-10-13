"""Paste Guard backend. Run: uvicorn app:app --host 127.0.0.1 --port 8765

Combines the secrets scanner with semantic similarity against the indexed
company documents and code, and returns allow / nudge / coach / block.
Documents and code have separate thresholds (env-configurable).
"""
import os
import re
import time
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import embedder
import secrets_scan
from audit import Audit
from config import CONFIG, CONFIG_PATH, VERSION
from chunking import DOC_EXT, extract_text, normalise, windows
from index import Index


THRESHOLDS = CONFIG["thresholds"]  # per kind; tuned with eval/run_eval.py (see eval/results.md)
HARD_SECRETS = {"private_key", "aws_access_key", "github_token", "openai_key", "slack_token"}
MAX_WINDOWS = int(os.environ.get("PG_MAX_WINDOWS", "48"))  # bounds CPU and RAM per request
MAX_FILE_BYTES = int(os.environ.get("PG_MAX_FILE_BYTES", str(10 * 1024 * 1024)))
LABEL = {"doc": "a confidential company document", "code": "company code"}

app = FastAPI(title="Paste Guard", version=VERSION)
_extra = [o for o in os.environ.get("PG_CORS_ORIGINS", "").split(",") if o]
app.add_middleware(CORSMiddleware, allow_origin_regex=r"chrome-extension://.*", allow_origins=_extra,
                   allow_methods=["GET", "POST"], allow_headers=["*"])
INDEX = Index()
AUDIT = Audit(CONFIG["audit"]["db"], CONFIG["audit"]["keep_days"])
ADMIN_HTML = (Path(__file__).with_name("admin.html")).read_text()


class CheckIn(BaseModel):
    text: str
    source: str | None = None


@app.get("/health")
def health():
    INDEX.refresh()
    return {"status": "ok", "version": VERSION, "model": embedder.MODEL_NAME, "index": INDEX.stats(),
            "thresholds": THRESHOLDS, "sites": CONFIG["sites"]["allowed"]}


def _local(request: Request):
    if request.client and request.client.host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
        raise HTTPException(403, "admin is only available from this machine (use an SSH tunnel)")


@app.get("/admin", response_class=HTMLResponse)
def admin(request: Request):
    _local(request)
    return ADMIN_HTML


@app.get("/admin/api")
def admin_api(request: Request):
    _local(request)
    INDEX.refresh()
    return {"version": VERSION, "config": str(CONFIG_PATH), "model": embedder.MODEL_NAME, "index": INDEX.stats(),
            "thresholds": THRESHOLDS, "sites": CONFIG["sites"]["allowed"],
            "counts_7d": AUDIT.counts(), "recent": AUDIT.recent(50)}


def prose_spans(text: str, words: int = 80, step: int = 40):
    """Character spans of paste prose: paragraphs, long ones split into ~80 word windows."""
    spans = []
    for m in re.finditer(r"\S(?:.*?\S)?(?=\n\s*\n|\s*$)", text, flags=re.S):
        toks = list(re.finditer(r"\S+", m.group(0)))
        if len(toks) < 6:
            continue
        base = m.start()
        if len(toks) <= words:
            spans.append((m.start(), m.end()))
            continue
        i = 0
        while True:
            part = toks[i:i + words]
            spans.append((base + part[0].start(), base + part[-1].end()))
            if i + words >= len(toks):
                break
            i += step
    return spans


def line_spans(text: str):
    """Character spans of 30-line windows (code mode)."""
    offs = [0]
    for ln in text.splitlines(keepends=True):
        offs.append(offs[-1] + len(ln))
    out = []
    for s, e, _ in windows(text, size=30, step=15, min_chars=40):
        out.append((offs[s - 1], offs[e]))
    return out


def semantic(text: str):
    """Embed paste windows (prose and line based), return per-window top hits."""
    spans = list(dict.fromkeys(prose_spans(text) + line_spans(text)))
    if len(text.split()) <= 400:
        spans.append((0, len(text)))  # whole paste as one more view
    spans = list(dict.fromkeys(spans))[:MAX_WINDOWS] or [(0, len(text))]
    vecs = embedder.embed([normalise(text[s:e]) for s, e in spans])
    out = []
    for (s, e), v in zip(spans, vecs):
        hits = INDEX.query(v, k=3)
        out.append({"span": [s, e], "hits": hits})
    return out


def level(hit) -> str | None:
    t = THRESHOLDS[hit["kind"]]
    for name in ("block", "coach", "nudge"):
        if hit["similarity"] >= t[name]:
            return name
    return None


RANK = {None: 0, "nudge": 1, "coach": 2, "block": 3}


def decide(text: str) -> dict:
    INDEX.refresh()
    findings = secrets_scan.scan(text)
    marks = secrets_scan.markers(text)
    types = {f["type"] for f in findings}
    per_window = semantic(text) if len(text.strip()) >= 20 else []

    # Best hit per (source, location), ranked by how far past its own kind threshold it is.
    best = {}
    for w in per_window:
        for h in w["hits"]:
            key = (h["kind"], h["path"], tuple(h["lines"]))
            if key not in best or h["similarity"] > best[key]["similarity"]:
                best[key] = {**h, "paste_span": w["span"],
                             "paste_excerpt": text[w["span"][0]:w["span"][1]][:300]}
    matches = sorted(best.values(), key=lambda h: (RANK[level(h)], h["similarity"] - THRESHOLDS[h["kind"]]["nudge"]),
                     reverse=True)[:5]
    for m in matches:
        m["level"] = level(m)
    top = matches[0] if matches and matches[0]["level"] else None
    sem = top["level"] if top else None

    if types & HARD_SECRETS:
        verdict, msg = "block", "This contains a live credential."
    elif sem == "block":
        verdict, msg = "block", f"This closely matches {LABEL[top['kind']]} ({top['path']})."
    elif sem == "coach":
        verdict = "coach"
        msg = (f"This looks like {LABEL[top['kind']]} ({top['path']}). "
               + ("Summarise it in your own words without names, numbers or specifics."
                  if top["kind"] == "doc" else "Share a minimal, generic version instead."))
    elif findings or marks:
        verdict = "coach"
        msg = ("This may contain a secret. Consider redacting it." if findings
               else "This is marked confidential. Check it is cleared for external AI tools.")
    elif sem == "nudge":
        verdict, msg = "nudge", f"Parts of this resemble {LABEL[top['kind']]} ({top['path']}). Double check before sending."
    else:
        verdict, msg = "allow", "No issues found."

    # One-click redaction: secrets first (character spans), then matched windows.
    spans = [(f["start"], f["end"], f"[REDACTED:{f['type']}]") for f in findings]
    for w in per_window:
        hit = w["hits"][0] if w["hits"] else None
        if hit and RANK[level(hit)] >= RANK["coach"] and w["span"] != [0, len(text)]:
            spans.append((w["span"][0], w["span"][1], f"[REDACTED:{'confidential_doc' if hit['kind'] == 'doc' else 'company_code'}]"))
    if top and RANK[sem] >= RANK["coach"] and not any(s[2].startswith("[REDACTED:c") for s in spans):
        spans.append((0, len(text), f"[REDACTED:{'confidential_doc' if top['kind'] == 'doc' else 'company_code'}]"))
    redacted = _apply(text, spans)
    return {"verdict": verdict, "message": msg, "findings": findings + marks, "matches": matches,
            "semantic_match": top, "redacted": redacted}


def _apply(text, spans):
    """Merge overlapping spans and replace each merged run with one label."""
    if not spans:
        return text
    spans.sort()
    merged = [list(spans[0])]
    for s, e, lab in spans[1:]:
        if s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
            if "confidential_doc" in lab or "company_code" in lab:
                merged[-1][2] = lab
        else:
            merged.append([s, e, lab])
    out, pos = [], 0
    for s, e, lab in merged:
        out.append(text[pos:s]); out.append(lab); pos = e
    out.append(text[pos:])
    return "".join(out)


@app.post("/check")
def check(req: CheckIn):
    t0 = time.time()
    res = decide(req.text)
    channel = "file" if " file:" in (req.source or "") else "paste"
    AUDIT.record(channel, (req.source or "").split(" ")[0], req.text, res, int((time.time() - t0) * 1000))
    return res


@app.post("/check_file")
async def check_file(file: UploadFile = File(...), source: str = Form("")):
    t0 = time.time()
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in DOC_EXT:
        raise HTTPException(415, f"unsupported file type {suffix or '(none)'}; supported: {sorted(DOC_EXT)}")
    data = await file.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(413, "file too large")
    try:
        text = extract_text(data, suffix)
    except Exception as ex:
        raise HTTPException(422, f"could not read {file.filename}: {ex}")
    res = decide(text)
    res["file"] = {"name": file.filename, "chars": len(text)}
    AUDIT.record("file", source, text, res, int((time.time() - t0) * 1000))
    return res
