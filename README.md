# Paste Guard

A proof of concept built by Sandeep Paluru for Eric at Sidekick Labs, to show how paste-level semantic matching could extend Sidekick's coverage. It is a working showcase, not a product.

Stops confidential company documents, source code and secrets from being pasted or uploaded into AI chat tools such as Claude and ChatGPT. Matching runs on your own machine or server with a local embedding model, so nothing is sent anywhere else.

- **Documents (primary):** board memos, contracts, pricing, HR and legal docs. Catches verbatim copies and also paraphrases, excerpts and summaries that keyword rules miss.
- **Code (second mode):** catches renamed and reformatted copies of functions from your repositories.
- **Secrets:** cloud keys, API keys (Anthropic, OpenAI, GitHub, Google, Stripe, Slack, Hugging Face, GitLab, npm, SendGrid, Twilio, Azure, xAI and others), private keys and database URLs with a password are always blocked. JWTs and password assignments are coached.

Each paste, file upload or drag-and-drop on a protected site gets a verdict: allow, nudge, coach or block. The overlay shows which document matched and why: a side-by-side "Your paste" and "Source" panel with the matching phrases highlighted. It also offers one-click redaction.

## Why this matched (0.7.0)
Every flagged hit in the `/check` and `/check_file` response has a `matches` list of up to three sentence pairs, so a reviewer (or a screen recording) can see the evidence instead of a bare score:

```
{"paste_span": [start, end], "paste_text": "...", "paste_marks": [[a, b]],      # indexes into the paste / the snippet
 "source_doc": "board-memo-acquisition-ferrolake.md", "source_text": "...", "source_span": [start, end],  # in the indexed passage
 "source_marks": [[a, b]], "kind": "ngram" | "tfidf" | "semantic", "score": 0.0-1.0}
```
`ngram` pairs share exact or near-exact phrases (word 3-grams), `tfidf` pairs share vocabulary, and `semantic` pairs are the best sentence alignment by MiniLM cosine for rewrites that share neither (they have no highlighted phrases, because there is no shared phrase to show). Snippets are sentence level and at most 240 characters. This only runs for flagged pastes; a benign paste has `matches: []` on every hit and pays nothing. `PG_EXPLAIN_HITS=0` turns it off. Latency numbers, including that the p95 under 100 ms goal is not met on the 2 vCPU VM, are in `eval/benchmarks.md`.

## Demo pages
Served by the backend, offline, no CDNs and no API key (the same host and port as the API, `http://127.0.0.1:8765` by default):
- `/demo/compare`: seven fixed example pastes (verbatim, paraphrase, partial excerpt, summary, code, secret, benign) through the regex and keyword baseline and through Paste Guard, with the matched document and latency. The header totals are read from `eval/bench_summary.json` and `eval/bench/fastpath.json` (regex recall 9.1% overall and 11.3% on documents, Paste Guard 94.6%). The examples were picked as the first of their type that regex misses and Paste Guard flags, and the page says so; the per-row note shows how often regex flags that type across the whole eval.
- `/demo/redteam`: press Start and 37 adversarial rewrites of the confidential acquisition memo (paraphrase, summary, translation, bullets, synonym swaps, typos, homoglyphs, splitting and more) go through `/check` at about one per second, with a live caught, nudged and slipped counter. The rewrites were generated in advance by Claude (Anthropic) and are labelled synthetic in `demo/redteam/rewrites.json`. Some of them do slip through, and the page shows that.

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
| `profile` | `"accurate"` or `"fast"` | Matching profile (default `accurate`), see Profiles |
| `[thresholds.doc]`, `[thresholds.code]` | `nudge`, `coach`, `block` | Cosine similarity levels per content kind |
| `[sites]` | `allowed` | AI sites to protect |
| `[audit]` | `db`, `keep_days` | Verdict log for the admin page |
| `[fast_path]` | `enabled`, `skip_below` | Two-step fast path (default on, `skip_below = 0.10`), see Fast path |

Environment variables override thresholds (`PG_T_DOC_COACH`, `PG_T_CODE_BLOCK`, and so on). `PG_FAST_PATH=0` turns the fast path off. `PG_NO_WARMUP=1` skips the model warm-up at startup.

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
 paste / file picker / drag-and-drop  ->  /check (text) or /check_file (PDF, DOCX, text, code)
 .txt/.md read in the browser             secrets and marker scan
 overlay: allow, nudge, coach, block  <-  windows of the paste embedded (all-MiniLM-L6-v2, ONNX, CPU)
 matched passage + source document        nearest passages in sqlite-vec (docs + code)
                                          + word 3-gram overlap with each passage
                                          (3-gram and TF-IDF run first; MiniLM only if needed)
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
kept: bge-base is better on summaries but needs 1.4 GB and is 7 times slower. Latency over HTTP in 0.5.1: p50 16 ms on an
8 vCPU machine, p50 208 ms on the 2 vCPU, 1 GB Techvista VM. Since 0.6.0 see Fast path below. How we got here, with numbers: `docs/OPTIMIZATION_LOG.md`.

## Privacy
- Paste text is processed in memory and never written to disk.
- The model is downloaded once and then runs offline.
- The admin page is only served to local connections.

## Tests
Run `.venv/bin/python -m pytest` from the repo root (plain `pytest`). It runs 101 pytest tests against the real model and index:
14 end-to-end tests in `tests/test_check.py`, 24 edge-case tests in `tests/test_edge_cases.py`, 7 'why this matched' tests in `tests/test_explain.py`, 4 and 5 demo page tests in `tests/test_demo_compare.py` and `tests/test_demo_redteam.py`, 46 secret format tests in `tests/test_secrets_formats.py` (fake keys are built at runtime, so no key-shaped literal is committed), and one test
(`tests/test_extension_js.py`) that runs the 16 jsdom tests of the extension content script in `tests/js/content.test.mjs`. The JS tests need `node`; `npm install` runs
automatically in `tests/js` the first time. If node or npm is missing, those tests are skipped. `pytest.ini` limits
collection to `tests/` and ignores `demo/`.

## Edge-case behaviour
- **Paste size:** pastes over 2 MB characters get HTTP 422. For long pastes and files (more than 48 windows), half the
  embedded windows are picked by TF-IDF score and half are sampled evenly, so a confidential section at the end of a
  1 MB paste or a 1500 paragraph docx is still checked.
- **Unicode tricks:** zero-width characters are stripped, text is NFKC normalized, and common Cyrillic and Greek
  look-alike letters are mapped to Latin before matching.
- **File types (`/check_file`, used by the file picker and drag-and-drop):** PDF, DOCX, plain text and code files are
  checked. Binary content disguised as text gets 422. Password-protected PDFs get 422 with a clear message; PDFs that
  only have an owner password are still checked. Images, archives and other types get 415.
- **Backend down (fail-open):** the paste goes through unchecked and the page shows "Paste Guard is offline, so this
  paste was not checked". Unreadable files show a toast naming the file and the reason.

## Profiles

`profile = "accurate"` is the default: MiniLM OR 3-gram OR TF-IDF for documents. Held-out document F1 0.97, recall 0.94,
false alarms 2.8%, /check p95 56 ms on a desktop CPU in 0.5.1 (22.5 ms in 0.6.0 with the fast path). On the 1 GB Techvista VM a short document paste check takes about
0.10 s end to end and the service uses about 370 MB of RAM.

`profile = "fast"` (or `PG_PROFILE=fast`) is the previous setup, MiniLM OR 3-gram without TF-IDF: held-out document
F1 0.94, recall 0.90, false alarms 2.8%. `"default"` is accepted as an alias for `accurate`.
Windows setup: `deploy/windows/`. Numbers: `eval/benchmarks.md`, reasoning: `docs/OPTIMIZATION_LOG.md`.

## Fast path (0.6.0)

Step 1 runs word 3-gram containment and TF-IDF on every window, which takes a few ms. The MiniLM embedding is skipped when a cheap check already reaches block (the embedding cannot raise the verdict past block, so the outcome is the same), or when the best TF-IDF score against any indexed passage is below 0.10 (almost no shared vocabulary). I took the idea from Google DeepMind's on-device Gemma scam detector: cheap classifier first, the heavier model only when needed. The model is still pretrained all-MiniLM-L6-v2 used zero-shot; only thresholds are tuned.

Measured on all 472 eval pastes with `eval/fastpath_eval.py` (deployed thresholds, flagged = coach or block): recall 0.946 and false alarm rate 2.5% with the fast path off and on. In-process p50 11.0 ms to 3.6 ms, p95 70.1 ms to 21.9 ms. MiniLM was skipped on 58.5% of the eval pastes. One verdict changed out of 472, a negative that went from nudge to allow. The eval set is mostly near-matches, so in daily use, where most pastes are unrelated text, the skip rate should be higher. I did not measure that.

Real `/check` calls over HTTP: on an 8 CPU box p50 19.1 ms to 7.3 ms and p95 56.1 ms to 22.5 ms. On the 2 CPU, 0.9 GB Techvista VM (shared, PG_THREADS=1) p50 130.6 ms to 84.0 ms and p95 801.9 ms to 397.2 ms. The VM tail comes from memory pressure and swap, not the model; on a normal laptop it meets p95 under 100 ms.

The backend now loads the model and runs one warm-up check at startup. The first `/check` after a restart went from 1.29 s to 0.024 s on the box (startup itself 0.45 s to 1.75 s) and from about 8.5 s to 0.18 s on the VM. `/health` shows the fast path settings and counters and `warmup_ms`.
