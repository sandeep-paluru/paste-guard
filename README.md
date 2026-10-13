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
                                          + word 3-gram overlap with each passage
 one-click redaction that keeps            per-kind bands -> verdict, matches, redacted text
 headings and signatures
```
Documents are split on paragraph boundaries into 120 to 200 word chunks with overlap, plus shorter 60 word passages so short excerpts still have a close neighbour. A paste is flagged when either its embedding is close to a passage or enough of its word 3-grams appear in one passage; the first catches rewording, the second catches partial copies.

## Results
Nothing is trained. Matching uses a public pretrained embedding model (all-MiniLM-L6-v2) zero-shot, plus a word 3-gram
fingerprint. The only values fitted to the eval data are the similarity thresholds.

From `eval/results.md` (472 samples, 18 confidential documents, one code repository), deployed bands, coach level:

| Kind | Method | Precision | Recall | F1 | False positive rate |
|---|---|---|---|---|---|
| Documents | Paste Guard hybrid (embedding OR 3-gram) | 1.00 | 0.87 | 0.93 | 0.01 |
| Documents | Embedding only | 1.00 | 0.76 | 0.86 | 0.01 |
| Documents | Regex and keyword baseline | 1.00 | 0.11 | 0.20 | 0.00 |
| Code | Paste Guard hybrid | 0.97 | 1.00 | 0.99 | 0.04 |
| Code | Regex and keyword baseline | 0.00 | 0.00 | 0.00 | 0.00 |

Those bands were picked on the same set. Held-out check (`eval/benchmarks.md`): thresholds tuned on pastes from 9 of
the 18 documents and scored on the other 9, then swapped. Documents: hybrid F1 0.94 (recall 0.90, FPR 0.03), MiniLM
alone 0.87 (recall 0.77), regex 0.20. Per transform (held-out, hybrid): verbatim 1.00, partial excerpts 0.92,
paraphrases 0.89, summaries 0.50, tone rewrites 0.50. Summaries and tone rewrites remain the weak spots. The top
match names the right source document 98% of the time.

Model benchmark (`eval/benchmarks.md`, charts `eval/bench_*.png`): MiniLM, bge-small, bge-base, jina code, nomic,
TF-IDF, 3-gram containment and MinHash on the same data, with latency and RAM. MiniLM plus the 3-gram fingerprint was
kept: bge-base is better on summaries but needs 1.4 GB and is 7 times slower. Latency over HTTP: p50 16 ms on an
8 vCPU machine, p50 208 ms on the 2 vCPU, 1 GB Techvista VM. How we got here, with numbers: `docs/OPTIMIZATION_LOG.md`.

## Privacy
- Paste text is processed in memory and never written to disk.
- The model is downloaded once and then runs offline.
- The admin page is only served to local connections.

## Tests
`.venv/bin/python -m pytest -q tests` runs end-to-end checks against the real model and index.
