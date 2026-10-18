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
            | POST http://127.0.0.1:8765/check
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

## Fast path (0.6.0)

Inside `/check`, `semantic()` runs in two steps. Step 1 computes word 3-gram containment and TF-IDF on every window. Step 2, the MiniLM embedding and the sqlite-vec search, only runs when it can change the verdict: it is skipped if a cheap check already reaches block, or if the best TF-IDF score against any indexed passage is below 0.10. On the 472 eval pastes this skips MiniLM 58.5% of the time with the same recall (0.946) and false alarm rate (2.5%). Configure with `[fast_path]` in `paste-guard.toml`; `PG_FAST_PATH=0` turns it off. At startup the backend loads the model and runs one warm-up check (`PG_NO_WARMUP=1` skips it).
