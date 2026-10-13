# Paste Guard

A proof of concept built by Sandeep Paluru for Eric at Sidekick Labs, to show how paste-level semantic matching could extend Sidekick's coverage. It is a working showcase, not a product.

Stops confidential company documents, source code and secrets from being pasted or uploaded into AI chat tools such as Claude and ChatGPT. Matching runs on your own machine or server with a local embedding model, so nothing is sent anywhere else.

- **Documents (primary):** board memos, contracts, pricing, HR and legal docs. Catches verbatim copies and also paraphrases, excerpts and summaries that keyword rules miss.
- **Code (second mode):** catches renamed and reformatted copies of functions from your repositories.
- **Secrets:** cloud keys, tokens, private keys and password assignments are always blocked or redacted.

Each paste, file upload or drag-and-drop on a protected site gets a verdict: allow, nudge, coach or block. The overlay shows which document matched and the matching passage, and offers one-click redaction.

## Run it (one command)
Requirements: Linux or macOS with Python 3.10+ (or Docker), about 600 MB RAM.

1. Edit `paste-guard.toml` and point `docs` and `code` at your folders.
2. Run one of:
   ```
   ./install.sh             # virtualenv, dependencies, model download, index build
   ./install.sh --service   # same, plus a systemd service that starts on boot
   docker compose up -d     # container; mount your folders in docker-compose.yml
   ```
3. In Chrome open `chrome://extensions`, turn on Developer mode, click **Load unpacked** and pick `extension/`. The toolbar icon shows a green dot when protection is active.

## Configuration (`paste-guard.toml`)
| Section | Keys | Meaning |
|---|---|---|
| `[index]` | `docs`, `code`, `db` | Folders to protect and where the index lives |
| `[server]` | `host`, `port` | Backend address (default 127.0.0.1:8765) |
| `[thresholds.doc]`, `[thresholds.code]` | `nudge`, `coach`, `block` | Cosine similarity levels per content kind |
| `[sites]` | `allowed` | AI sites to protect |
| `[audit]` | `db`, `keep_days` | Verdict log for the admin page |

Environment variables override thresholds (`PG_T_DOC_COACH`, `PG_T_CODE_BLOCK`, and so on).

## Commands
```
./pasteguard serve      # start the backend
./pasteguard reindex    # rebuild after documents change; the running server picks it up automatically
./pasteguard status     # health check
./pasteguard eval       # run the evaluation
```

## Admin page
Open `http://127.0.0.1:8765/admin` on the backend machine (or through an SSH tunnel). It shows indexed passages, thresholds, verdict counts for the last 7 days and recent checks. The log never stores content: only a SHA-256 hash, the length, the verdict and the matched source name.

## How it works
```
 Chrome extension                         Paste Guard backend (local or company server)
 paste / file picker / drag-and-drop  ->  /check (text) or /check_file (PDF, DOCX)
 .txt/.md read in the browser             secrets and marker scan
 overlay: allow, nudge, coach, block  <-  windows of the paste embedded (all-MiniLM-L6-v2, ONNX, CPU)
 matched passage + source document        nearest passages in sqlite-vec (docs + code)
 one-click redaction                      per-kind thresholds -> verdict, matches, redacted text
```
Documents are split on paragraph boundaries into 120 to 200 word chunks with overlap, plus shorter 60 word passages so short excerpts still have a close neighbour.

## Results
From `eval/results.md` (472 samples, 18 confidential documents, one code repository):

| Kind | Method | Precision | Recall | F1 | False positive rate |
|---|---|---|---|---|---|
| Documents | Paste Guard (coach level) | 0.99 | 0.80 | 0.88 | 0.03 |
| Documents | Paste Guard (any warning, nudge level) | 0.98 | 0.81 | 0.89 | 0.07 |
| Documents | Regex and keyword baseline | 1.00 | 0.11 | 0.20 | 0.00 |
| Code | Paste Guard (coach level) | 0.97 | 0.92 | 0.95 | 0.04 |
| Code | Regex and keyword baseline | 0.00 | 0.00 | 0.00 | 0.00 |

At the coach level, verbatim excerpts are caught 94% of the time (regex 14%), prompt-wrapped pastes 92% (regex 19%) and paraphrases 81% (regex 3%). Summaries (56%), partial excerpts (57%) and tone rewrites (50%) are the hardest. The top match names the right source document 95% of the time. Thresholds were tuned on this set, so treat these as in-sample numbers. Full breakdown and chart: `eval/results.md`.

## Privacy
- Paste text is processed in memory and never written to disk.
- The model is downloaded once and then runs offline.
- The admin page is only served to local connections.

## Tests
`.venv/bin/python -m pytest -q tests` runs end-to-end checks against the real model and index.
