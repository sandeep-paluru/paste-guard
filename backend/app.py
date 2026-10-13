"""Paste Guard local backend. Run: uvicorn app:app --port 8765"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import secrets_scan

app = FastAPI(title="Paste Guard")
app.add_middleware(CORSMiddleware, allow_origin_regex=r"chrome-extension://.*",
                   allow_methods=["*"], allow_headers=["*"])


class CheckIn(BaseModel):
    text: str
    source: str | None = None


@app.get("/health")
def health():
    return {"status": "ok", "semantic_index": "not built (day 2)"}


@app.post("/check")
def check(req: CheckIn):
    findings = secrets_scan.scan(req.text)
    # TODO(day 2): add semantic match score from embedder + index.
    types = {f["type"] for f in findings}
    if types & {"private_key", "aws_access_key", "github_token", "openai_key", "slack_token"}:
        verdict, msg = "block", "This paste looks like it contains a live credential."
    elif findings:
        verdict, msg = "coach", "This paste may contain a secret. Consider redacting it."
    else:
        verdict, msg = "allow", "No issues found."
    return {"verdict": verdict, "message": msg, "findings": findings,
            "semantic_match": None, "redacted": secrets_scan.redact(req.text, findings)}
