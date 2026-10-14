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
from pydantic import BaseModel, Field

import embedder
import explain
import secrets_scan
from audit import Audit
from config import CONFIG, CONFIG_PATH, VERSION
from chunking import UPLOAD_EXT, NotText, clean, extract_text, line_spans, normalise, prose_spans
from index import Index


THRESHOLDS = CONFIG["thresholds"]  # embedding cosine bands per kind; see eval/results.md and eval/benchmarks.md
FINGERPRINT = CONFIG["fingerprint"]  # word 3-gram containment levels per kind (hybrid matching)
TFIDF = CONFIG["tfidf"]  # TF-IDF cosine levels per kind; only used when the profile enables it
PROFILE = CONFIG["profile"]
FAST = CONFIG["fast_path"]  # two-step matching: cheap lexical checks first, MiniLM only when uncertain
STATS = {}  # fast path counters, shown on /health
# Live credentials always block. password_assignment and jwt stay a softer "may contain a secret" coach.
HARD_SECRETS = {"private_key", "aws_access_key", "aws_temp_key", "github_token", "github_pat_fine_grained",
                "anthropic_key", "openai_key", "xai_key", "google_api_key", "google_oauth_client_secret",
                "stripe_key", "slack_token", "slack_webhook", "huggingface_token", "gitlab_token", "npm_token",
                "sendgrid_key", "twilio_key", "azure_storage_key", "db_url_password"}
MAX_WINDOWS = int(os.environ.get("PG_MAX_WINDOWS", "48"))  # bounds CPU and RAM per request
MAX_FILE_BYTES = int(os.environ.get("PG_MAX_FILE_BYTES", str(10 * 1024 * 1024)))
MAX_CHARS = int(os.environ.get("PG_MAX_CHARS", str(2 * 1024 * 1024)))  # longer pastes are rejected with HTTP 422
LABEL = {"doc": "a confidential company document", "code": "company code"}

app = FastAPI(title="Paste Guard", version=VERSION)


@app.on_event("startup")
def _warm_up():
    """Load the model and run one embedding at startup so the first real paste is not slow."""
    if os.environ.get("PG_NO_WARMUP"):
        return
    t0 = time.time()
    embedder.embed(["warm up"])
    decide("Warm-up request: load the index, the TF-IDF vocabulary and the 3-gram fingerprints once at startup.")
    STATS["warmup_ms"] = round((time.time() - t0) * 1000)
_extra = [o for o in os.environ.get("PG_CORS_ORIGINS", "").split(",") if o]
app.add_middleware(CORSMiddleware, allow_origin_regex=r"chrome-extension://.*", allow_origins=_extra,
                   allow_methods=["GET", "POST"], allow_headers=["*"])
INDEX = Index()
AUDIT = Audit(CONFIG["audit"]["db"], CONFIG["audit"]["keep_days"])
ADMIN_HTML = (Path(__file__).with_name("admin.html")).read_text()


class CheckIn(BaseModel):
    text: str = Field(max_length=MAX_CHARS)
    source: str | None = None


@app.get("/health")
def health():
    INDEX.refresh()
    return {"status": "ok", "version": VERSION, "model": embedder.MODEL_NAME, "index": INDEX.stats(),
            "profile": PROFILE, "thresholds": THRESHOLDS, "fingerprint": FINGERPRINT,
            "tfidf": TFIDF if TFIDF["enabled"] else None, "fast_path": {**FAST, "stats": STATS},
            "sites": CONFIG["sites"]["allowed"]}


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
            "profile": PROFILE, "thresholds": THRESHOLDS, "fingerprint": FINGERPRINT,
            "tfidf": TFIDF if TFIDF["enabled"] else None, "sites": CONFIG["sites"]["allowed"],
            "counts_7d": AUDIT.counts(), "recent": AUDIT.recent(50)}


def semantic(text: str):
    """Embed paste windows (prose and line based), return per-window top hits."""
    spans = list(dict.fromkeys(prose_spans(text) + line_spans(text)))
    if len(text.split()) <= 400:
        spans.append((0, len(text)))  # whole paste as one more view
    spans = list(dict.fromkeys(spans))
    if len(spans) > MAX_WINDOWS:
        # Huge paste or file: embedding every window would be slow, so pick which ones to embed.
        # Half go to the windows with the highest TF-IDF score against the index (a sparse product,
        # a few ms even for thousands of windows), half are sampled evenly across the text.
        # This way a confidential section buried at the end of a long paste is still seen.
        scores = [max((h["similarity"] for h in hs), default=0.0)
                  for hs in INDEX.tfidf([clean(text[s:e]) for s, e in spans])]
        top = sorted(range(len(spans)), key=lambda i: scores[i], reverse=True)[:MAX_WINDOWS // 2]
        step = len(spans) / (MAX_WINDOWS - len(top))
        pick = set(top) | {int(i * step) for i in range(MAX_WINDOWS - len(top))}
        spans = [spans[i] for i in sorted(pick)]
    spans = spans or [(0, len(text))]
    # Step 1 (cheap, a few ms): 3-gram containment and TF-IDF on every window.
    fps = [INDEX.fingerprint(text[s:e], FINGERPRINT["min_shingles"]) for s, e in spans]
    lex_all = INDEX.tfidf([clean(text[s:e]) for s, e in spans])
    lex = lex_all if TFIDF["enabled"] else [[] for _ in spans]
    vecs = [None] * len(spans)
    STATS["last_path"] = "embedding"
    if FAST["enabled"]:
        cheap = [h for hs in fps + lex for h in hs]
        top_tf = max((h["similarity"] for hs in lex_all for h in hs), default=0.0)
        if any(level(h) == "block" for h in cheap):
            STATS["last_path"] = "cheap_block"  # already the strongest verdict; the embedding cannot raise it
        elif top_tf < FAST["skip_below"]:
            STATS["last_path"] = "cheap_clear"  # almost no shared vocabulary with any indexed passage
    if STATS["last_path"] == "embedding":
        # Step 2: MiniLM only when step 1 is uncertain.
        vecs = embedder.embed([normalise(text[s:e]) for s, e in spans])
    STATS[STATS["last_path"]] = STATS.get(STATS["last_path"], 0) + 1
    if STATS["last_path"] == "embedding":
        explain.seed([text[s:e] for s, e in spans], vecs)
    out = []
    for (s, e), v, fp, tf in zip(spans, vecs, fps, lex):
        hits = (INDEX.query(v, k=3) if v is not None else []) + fp + tf
        hits.sort(key=lambda h: (RANK[level(h)], margin(h)), reverse=True)
        out.append({"span": [s, e], "hits": hits})
    return out


RANK = {None: 0, "nudge": 1, "coach": 2, "block": 3}


def _bands(hit):
    if hit.get("method") == "fingerprint":
        return FINGERPRINT[hit["kind"]]
    if hit.get("method") == "tfidf":
        return TFIDF[hit["kind"]]
    return THRESHOLDS[hit["kind"]]


def level(hit) -> str | None:
    t = _bands(hit)
    for name in ("block", "coach", "nudge"):
        if name in t and hit["similarity"] >= t[name]:
            return name
    return None


def margin(hit) -> float:
    """How far past its lowest band a hit is, comparable across methods."""
    t = _bands(hit)
    return hit["similarity"] - min(t.values())


def decide(text: str) -> dict:
    INDEX.refresh()
    findings = secrets_scan.scan(text)
    marks = secrets_scan.markers(text)
    types = {f["type"] for f in findings}
    per_window = semantic(text) if len(clean(text).strip()) >= 20 else []

    # Best hit per (source, location), ranked by how far past its own kind threshold it is.
    best = {}
    for w in per_window:
        for h in w["hits"]:
            key = (h["kind"], h["path"], tuple(h["lines"]), h.get("method"))
            if key not in best or h["similarity"] > best[key]["similarity"]:
                best[key] = {**h, "paste_span": w["span"],
                             "paste_excerpt": text[w["span"][0]:w["span"][1]][:300]}
    matches = sorted(best.values(), key=lambda h: (RANK[level(h)], margin(h)), reverse=True)[:5]
    for m in matches:
        m["level"] = level(m)
    explain.explain(text, matches)  # "why this matched" pairs, only for hits with a level (flagged pastes)
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

    # One-click redaction. Secrets are replaced in place. Lines covered by a matched window are replaced
    # with a pointer to the matching source passage, but headings and code signatures are kept so the user
    # still sees the structure of what they pasted and can ask a generic question about it.
    secret_spans = [(f["start"], f["end"], f"[REDACTED:{f['type']}]") for f in findings]
    flagged = []
    for w in per_window:
        hit = w["hits"][0] if w["hits"] else None
        if hit and RANK[level(hit)] >= RANK["coach"]:
            flagged.append((w["span"][0], w["span"][1], hit))
    # The whole-paste view only counts when no narrower window matched.
    narrow = [f for f in flagged if [f[0], f[1]] != [0, len(text)]]
    redacted = redact(text, narrow or flagged, secret_spans)
    return {"verdict": verdict, "message": msg, "findings": findings + marks, "matches": matches,
            "semantic_match": top, "redacted": redacted}


KEEP_LINE = re.compile(r"^\s*(#{1,6}\s|(async\s+)?def\s|class\s|function\s|export\s|public\s|private\s|func\s|fn\s)")


def _keep(line: str) -> bool:
    """Headings and code signatures survive redaction; bodies do not."""
    t = line.strip()
    if not t:
        return True
    if KEEP_LINE.match(line):
        return True
    words = t.split()
    return len(words) <= 8 and not t.endswith((".", ",", ";")) and not any(ch.isdigit() for ch in t) \
        and t[0].isupper() and not ("=" in t or "(" in t or "|" in t)


def _apply_spans(text, spans, offset=0):
    out, pos = [], 0
    for s, e, lab in sorted(spans):
        s, e = max(s - offset, 0), min(e - offset, len(text))
        if s < pos or s >= len(text):
            continue
        out.append(text[pos:s]); out.append(lab); pos = e
    out.append(text[pos:])
    return "".join(out)


def redact(text: str, flagged, secret_spans) -> str:
    """Line-level redaction with source pointers. flagged: (start, end, hit) character windows."""
    lines = text.splitlines(keepends=True)
    out, pos, run = [], 0, None  # run: {path: [unit, a, b]} for the current block of removed lines

    def close():
        if run:
            parts = [f"{p} {u} {a}-{b}" for p, (u, a, b) in list(run.items())[:3]]
            out.append("[REDACTED: matches " + "; ".join(parts) + "]\n")

    for ln in lines:
        s, e = pos, pos + len(ln)
        pos = e
        mid = (s + e) / 2
        hits = [h for fs, fe, h in flagged if fs <= mid < fe] if ln.strip() else []
        if hits and not _keep(ln):
            run = run or {}
            for h in hits:
                u = "paragraphs" if h["kind"] == "doc" else "lines"
                a, b = h["lines"]
                if h["path"] in run:
                    run[h["path"]][1] = min(run[h["path"]][1], a); run[h["path"]][2] = max(run[h["path"]][2], b)
                else:
                    run[h["path"]] = [u, a, b]
            continue
        if run and not ln.strip():
            continue  # blank lines inside a removed block collapse into the label
        close(); run = None
        out.append(_apply_spans(ln, [x for x in secret_spans if s <= x[0] < e], s))
    close()
    res = "".join(out)
    return res if text.endswith("\n") or not res.endswith("\n") else res[:-1]


def _site(source: str, request: Request) -> str:
    """Site for the verdict log: the extension sends the page hostname; direct API calls are labelled."""
    site = (source or "").split(" ")[0].strip()
    if site:
        return site
    ref = request.headers.get("referer") or request.headers.get("origin") or ""
    host = re.sub(r"^[a-z-]+://", "", ref).split("/")[0]
    if host and not ref.startswith("chrome-extension://"):
        return host
    return "direct API call"


@app.post("/check")
def check(req: CheckIn, request: Request):
    t0 = time.time()
    res = decide(req.text)
    channel = "file" if " file:" in (req.source or "") else "paste"
    AUDIT.record(channel, _site(req.source, request), req.text, res, int((time.time() - t0) * 1000))
    return res


@app.post("/check_file")
async def check_file(request: Request, file: UploadFile = File(...), source: str = Form("")):
    t0 = time.time()
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in UPLOAD_EXT:
        raise HTTPException(415, f"unsupported file type {suffix or '(none)'}; supported: {sorted(UPLOAD_EXT)}")
    data = await file.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(413, "file too large")
    try:
        text = extract_text(data, suffix)
    except NotText as ex:
        raise HTTPException(422, f"could not check {file.filename}: {ex}")
    except Exception as ex:
        raise HTTPException(422, f"could not read {file.filename}: {type(ex).__name__}")
    res = decide(text)
    res["file"] = {"name": file.filename, "chars": len(text)}
    AUDIT.record("file", _site(source, request), text, res, int((time.time() - t0) * 1000))
    return res
