# Architecture

```
+-------------------------+
| AI tool page            |   claude.ai, chatgpt.com
| (user pastes text)      |
+-----------+-------------+
            | paste event
            v
+-------------------------+
| Content script          |   grabs text, shows overlay
+-----------+-------------+
            | chrome.runtime message
            v
+-------------------------+
| Service worker (MV3)    |
+-----------+-------------+
            | POST http://localhost:8765/check
            v
+---------------------------------------------------+
| Localhost API (FastAPI)                           |
|   +-----------+  +--------------+  +-----------+  |
|   | Embedder  |->| Vector index |  | Secrets / |  |
|   | (local)   |  | sqlite-vec   |  | PII scan  |  |
|   +-----------+  +--------------+  +-----------+  |
|                 \        |        /               |
|                  v       v       v                |
|                  verdict: allow / nudge /         |
|                  coach / block (+ redacted text)  |
+---------------------------------------------------+
            |
            v
   Overlay in page, one-click redaction
   Nothing leaves the machine.
```

## Who does what

| Step | Tool | Notes |
|---|---|---|
| Extension scaffold, manifest, paste hook | Cursor | Day 1 |
| Verdict overlay UI | Cursor | Day 1 |
| FastAPI backend, /check, /health | Cursor | Day 1 |
| Embedding service and indexing (sqlite-vec) | Cursor | Day 2 |
| Secrets and PII scanner | Cursor | Day 3 |
| Eval harness | Cursor | Day 3 |
| Disguised copies and negatives generation | Claude | about 500 samples |
| Nudge, coach, block copy | Claude | short, plain user text |
| Threshold tuning from eval results | Claude | reads results, proposes thresholds |
| README polish | Claude | Day 3 |
| Email to Eric | Claude | short, not begging |
