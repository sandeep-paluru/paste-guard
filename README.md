# Paste Guard with Prompt Diff

Chrome extension proof of concept. It checks text you paste into Claude or ChatGPT against local rules (and, from Day 2, against your own codebase) and shows a verdict: allow, nudge, coach, or block. Everything runs on your machine.

## 5-minute setup
1. Start the backend:
   ```
   cd backend
   python3 -m venv .venv && . .venv/bin/activate
   pip install -r requirements.txt
   uvicorn app:app --port 8765
   ```
2. Check it: `curl http://localhost:8765/health`
3. In Chrome open `chrome://extensions`, turn on Developer mode, click "Load unpacked", pick the `extension/` folder.
4. Open claude.ai or chatgpt.com and paste something like `api_key = "abcdef123456"`. An overlay shows the verdict.

## Status
- Day 1 (done): paste hook, service worker, overlay, backend with regex secrets check.
- Day 2: local embeddings and sqlite-vec index.
- Day 3: fuller secrets and PII layer, eval harness, README and screenshots.

See `docs/ARCHITECTURE.md` and `eval/README.md`.
