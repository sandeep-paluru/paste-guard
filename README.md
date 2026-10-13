# Paste Guard with Prompt Diff

Chrome extension proof of concept. It checks text you paste into Claude or ChatGPT for secrets and for semantic matches against your own codebase, then shows a verdict: allow, nudge, coach, or block, with one-click redaction. A real local embedding model (all-MiniLM-L6-v2, ONNX on CPU) and a sqlite-vec index do the matching. Nothing leaves the machine.

## 5-minute setup
1. Install and index a repo (the demo uses the public pallets/itsdangerous repo as "company code"):
   ```
   python3 -m venv .venv && . .venv/bin/activate
   pip install -r backend/requirements.txt
   git clone --depth 1 https://github.com/pallets/itsdangerous demo/company-repo
   cd backend && python index.py build ../demo/company-repo
   uvicorn app:app --host 127.0.0.1 --port 8765
   ```
2. Check it: `curl http://localhost:8765/health`
3. In Chrome open `chrome://extensions`, turn on Developer mode, click "Load unpacked", pick `extension/`.
4. Open claude.ai or chatgpt.com and paste a renamed copy of a function from the indexed repo, or a fake AWS key. The overlay offers "Paste redacted", "Paste anyway" (not on block), and "Cancel".

## Remote backend
Open the extension options and set the backend URL (for example a VM URL). Chrome asks for permission for that one origin only. For browser origins other than the extension, set `PG_CORS_ORIGINS`.

## Verdict logic
- Live credential (AWS, GitHub, OpenAI, Slack, private key) or similarity >= 0.90: block
- Similarity >= 0.80 or a softer secret finding: coach
- Similarity >= 0.70: nudge
- Otherwise: allow

Thresholds are env vars (`PG_T_NUDGE`, `PG_T_COACH`, `PG_T_BLOCK`).

## Tests
`python tests/test_check.py` runs the real model and index: a disguised function gets coach (similarity about 0.89), unrelated code gets allow (about 0.17), an AWS key gets block.

## Status
- Day 1 and Day 2 done: paste hook, overlay with redaction, configurable backend, real embeddings, sqlite-vec index, indexing CLI.
- Day 3: fuller secrets and PII layer, eval harness, screenshots.
