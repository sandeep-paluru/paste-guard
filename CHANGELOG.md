# Changelog

## 0.11.0 (2026-10-25)

- `./pasteguard scan` honors `pasteguard:ignore` on the same line as a finding, and `pasteguard:ignore-next-line` on the line above. An optional `=rule`, or a comma-separated list, limits that to named detectors. The marker text is enough, so `#`, `//`, `--`, `/* */`, `<!-- -->`, and `;` all work. A secret that spans several lines is suppressed when the marker is on its first line. Suppressed findings are not printed and do not change the exit code. The summary counts them as `N inline`, separate from allowlisted and baseline counts. JSON leaves them out of the list. SARIF keeps them, with a suppression of kind `inSource` and status `accepted`, so GitHub code scanning can hide the alert. `--no-inline-ignore` turns the markers off. `--report-unused-ignores` prints `path:line unused pasteguard:ignore` for markers that suppressed nothing and exits 1 if any exist. An unknown rule name warns on stderr. In `--staged` and `--diff-base`, a marker in the new file counts even when that line was not added. The allowlist still runs first. Tests in `tests/test_scan_inline.py`. Plain pytest is 254 tests (was 225).
- Version is 0.11.0 in `VERSION`, the extension manifest, `/health` and the compose image tag.

## 0.10.0 (2026-10-25)

- `./pasteguard scan --staged` scans only lines added in the index (`git diff --cached`) and reads the staged blob, so a pre-commit hook checks the text that will be committed. `./pasteguard scan --diff-base REF` scans only lines added since the merge-base of REF and HEAD (`git diff REF...HEAD`). That compares commits, so uncommitted edits are not included. A secret is reported only when every line it touches was added. One that was already in the file, or that sits on a line the diff left alone, is left out. Line numbers are positions in the new file. Deleted files and binary diffs are skipped. Renames are followed. `--exclude`, the vendor and binary skips, the allowlist, `--baseline`, and `--fail-on` still apply. A path argument, a missing git repo, or a bad ref exits 2. `.pre-commit-hooks.yaml` adds `pasteguard-scan-staged`. Tests in `tests/test_scan_diff.py`. Plain pytest is 225 tests (was 208).
- Version is 0.10.0 in `VERSION`, the extension manifest, `/health` and the compose image tag.

## 0.9.0 (2026-10-24)

- `./pasteguard scan --format sarif` writes SARIF 2.1.0 to stdout (the summary stays on stderr) for GitHub code scanning. One rule per detector, with a short description. Each result has a file URI relative to the working directory, `startLine`, `startColumn`, and a message that is only the mask. The secret is not written. Exit codes and `--fail-on` are unchanged. `--write-baseline PATH` records each current finding as its path, detector, and the sha256 of the detector name, a NUL byte, and the raw value. `--baseline PATH` drops findings already in that file from the report and from the exit code. The text summary, and the JSON and SARIF summaries on stderr, include how many were suppressed. The allowlist runs first, so an allowlisted value is counted as allowlisted and is not written to a baseline. Stdlib only. Tests in `tests/test_scan_command.py`. Plain pytest is 208 tests (was 203).
- Version is 0.9.0 in `VERSION`, the extension manifest, `/health` and the compose image tag.

## 0.8.0 (2026-10-23)

- `./pasteguard scan` checks files, directories, or stdin with the secrets scanner. Same rules and overlap handling as the extension, and the same `[secrets]` allowlist (`paste-guard.toml`, `PG_SECRETS_ALLOWLIST`, `PG_SECRETS_EXAMPLES`). It does not load the model, the index, or the server. Directories are walked recursively, skipping binary files, `.git`, vendor directories (`node_modules`, `vendor`, `.venv`), and tool caches (`__pycache__`, `.pytest_cache`). `--exclude GLOB` may be repeated. Each finding is one line, `path:line:col rule severity`, plus a mask of the first 4 characters and the length. The secret itself is not printed. `--format json` prints a JSON list on stdout and the summary on stderr. The text report ends with a summary line that includes how many hits were allowlisted. Exit 0 when nothing blocks, 1 when a block-level finding remains, 2 on a usage error. `--fail-on coach` also fails on JWTs and password assignments. `.pre-commit-hooks.yaml` adds the `pasteguard-scan` hook. Tests in `tests/test_scan_command.py`. Plain pytest is 203 tests (was 188).
- Version is 0.8.0 in `VERSION`, the extension manifest, `/health` and the compose image tag.

## 0.7.2 (2026-10-22)
- Secrets allowlist. Exact values, regexes, and sha256 fingerprints in `[secrets]` (`paste-guard.toml`) or in a file (`file`, or `PG_SECRETS_ALLOWLIST`) are dropped from the verdict and counted. The `/check` response includes `allowlisted`, and the `/logs` line says `allowlisted: 1` without the value. `./pasteguard fingerprint` prints the sha256 of a value read from stdin. The default examples are four public documentation samples: the AWS example access key `AKIAIOSFODNN7EXAMPLE`, the AWS example secret, the Stripe docs test key, and the jwt.io sample token. `examples = false` or `PG_SECRETS_EXAMPLES=0` turns those off. Any other key, including a different `sk_test_` key, still blocks. The compare demo's secret row uses a synthetic access key so it still blocks. Tests in `tests/test_secret_allowlist.py`. Plain pytest is 188 tests (was 174).
- Version is 0.7.2 in `VERSION`, the extension manifest, `/health` and the compose image tag.

## 0.7.1 follow-up (2026-10-21)
- Secrets scanner: password assignments pasted from `.env` files and config snippets are detected. Prefixed names (`DB_PASSWORD`, `AWS_SECRET_ACCESS_KEY`), `client_secret`, `access_token`, `auth_token`, and `private_key_id` match with a quoted or unquoted value. Empty values, `${VAR}`, `$VAR`, `<your-password>`, `changeme`, `xxxx`, `***`, `your_api_key_here`, `example`, `null`, `None`, and other short placeholders are ignored. A sentence such as "the password policy is: rotate every 90 days" is not a finding. An unquoted value is kept when it has a digit, a `+/=` symbol, or 16 or more characters. A quoted value of 8 or more characters is kept too, which is the previous quoted-password behavior, once placeholders are removed. Database URLs with a password also cover redis, rediss, amqp, amqps, mssql (including `mssql+pyodbc`), and sqlserver. A specific provider rule still wins when it overlaps the generic assignment. Redaction still replaces the whole assignment. Tests in `tests/test_secrets_formats.py`. Plain pytest is 174 tests.

## 0.7.1 follow-up (2026-10-19)
- A dropped PDF now keeps a blank line where the page has a gap between paragraphs. pypdf's plain extract was joining those lines, so a code block inside a longer file was scored with the prose around it and could miss a coach that the same text got when pasted. `Signing Module Review` is coached either way now. The index still uses the plain extract, so the tuned thresholds stay where they are. Test: `tests/test_pdf_paragraphs.py`.

## 0.7.1 (2026-10-14)
- **Live log.** New `/logs` page (local only) that shows every check as it happens: time, site, paste or file, verdict, matched source, best MiniLM, 3-gram and TF-IDF scores, whether the fast path skipped MiniLM, latency, and a short SHA-256 prefix with the length. Never the text. It polls the new `/logs/api?after=<id>` endpoint; events are kept in memory only (`backend/livelog.py`, last 500).
- The server console prints one readable line per check with the same fields (`PG_CONSOLE_LOG=0` turns it off).
- Windows: `deploy/windows/start-backend-with-logs.cmd` runs the backend in a visible console without access-log noise, and `deploy/windows/stop-backend.cmd` stops a running one. Both work without admin.
- Tests: 108 pytest tests (was 101), new `tests/test_livelog.py`. Version is 0.7.1 in `VERSION`, the extension manifest, `/health` and the compose image tag.

## 0.7.0 (2026-10-14)
- **Why this matched.** Flagged hits in `/check` and `/check_file` carry a `matches` list: up to three sentence pairs with `paste_span`, `paste_text`, `source_doc`, `source_text`, `source_span`, highlight marks, `kind` (`ngram`, `tfidf` or `semantic`) and `score`. Phrase spans come from the existing 3-gram and TF-IDF overlap; rewrites that share neither get the best sentence alignment by MiniLM cosine, in one embedding batch with cached vectors and the window vectors the matcher already has. Benign pastes never pay for it. `PG_EXPLAIN_HITS=0` turns it off. New `backend/explain.py`.
- Extension overlay: side-by-side "Your paste" and "Source" panel, at most three rows, 14 px text, matched phrases in `<mark>`, everything HTML escaped.
- `/demo/compare`: regex baseline versus Paste Guard on seven fixed examples, with totals read from the eval result files. The baseline moved to `backend/regex_baseline.py` (`eval/baseline.py` re-exports it) so the server and the eval share one implementation.
- `/demo/redteam`: 37 pre-generated adversarial rewrites of the acquisition memo (`demo/redteam/rewrites.json`, generated in advance by Claude, labelled synthetic) replayed through `/check` with a live counter. No API key or model call at runtime.
- `eval/http_latency.py` also reports p50 and p95 for flagged pastes only. Dockerfile ships the demo data.
- Latency, measured honestly: on the 2 vCPU, 0.9 GB VM, which was swapping heavily, flagged p95 was 290 ms in the calmest run and over 1 s in the worst, with and without the feature, so the goal of p95 under 100 ms for flagged pastes is not met there. The feature adds about 2 ms at p50 once sentence vectors are cached and 83 ms at p50 the first time a passage is explained. Details in `eval/benchmarks.md`.
- Tests: 101 pytest tests (was 84), 16 jsdom tests (was 13). Version is 0.7.0 in `VERSION`, the extension manifest, `/health` and the compose image tag.

## 0.6.0 Windows follow-up (2026-10-14)
- Secrets scanner: a specific credential rule now wins over the generic `password_assignment` rule when they overlap. Before, `api_key="sk-ant-..."` (the usual way a key appears in code) was reported as a password assignment and only coached; now it is `anthropic_key` and blocks. Same for OpenAI, AWS and other keys inside `password = '...'`. Test added.
- `deploy/windows/setup.ps1` tested end to end on Windows 10 with Python 3.13.7, no admin: no winget, finds the per-user python.org Python and git outside PATH, autostarts via a Startup-folder shortcut instead of a Scheduled Task, and does not start a second server if port 8765 is taken.
- `eval/http_latency.py` runs on Windows (latency only there). Windows PC (8 CPU, 15.6 GB): p50 21 ms, p95 46 ms over 200 `/check` calls, warm-up 1.9 s at startup.
- Index paths are stored with forward slashes on every OS.
- `tests/test_extension_js.py` calls npm by its resolved path, so it runs on Windows (where npm is `npm.cmd`).

## 0.6.0 (2026-10-14)
- Two-step fast path in `semantic()` (`backend/app.py`). Step 1 runs 3-gram containment and TF-IDF on every window, which takes a few ms. MiniLM is skipped when a cheap check already reaches block (the embedding cannot raise the verdict past block), or when the best TF-IDF score against any indexed passage is below 0.10. Config: `[fast_path] enabled = true, skip_below = 0.10`. `PG_FAST_PATH=0` turns it off. The idea comes from the two-stage design of Google DeepMind's on-device Gemma scam detector (October 2026): a cheap classifier first, the heavier model only when needed.
- Measured with the new `eval/fastpath_eval.py` on all 472 eval pastes, fast path off and on, deployed thresholds, flagged = coach or block. Recall 0.946 and false alarm rate 2.5% both ways. In-process p50 11.0 ms to 3.6 ms, p95 70.1 ms to 21.9 ms. MiniLM skipped on 58.5% of the eval pastes. One verdict changed out of 472: a negative went from nudge to allow. Results in `eval/bench/fastpath.json`, chart `eval/bench_fastpath.png`.
- HTTP latency of real `/check` calls (`eval/http_latency.py`). This box (8 CPU): p50 19.1 ms to 7.3 ms, p95 56.1 ms to 22.5 ms. Techvista VM (2 CPU, 0.9 GB, shared, PG_THREADS=1): p50 130.6 ms to 84.0 ms, p95 801.9 ms to 397.2 ms. The VM tail is memory pressure and swap, not the model.
- Cold start: the backend loads the model and runs one warm-up check at startup (`PG_NO_WARMUP=1` skips it). First `/check` after a restart: 1.29 s to 0.024 s on this box (startup itself 0.45 s to 1.75 s), about 8.5 s to 0.18 s on the VM (warm-up takes 18 s at startup there). `/health` now shows the fast path settings and counters, and `warmup_ms`.
- Secrets scanner: new rules for Anthropic keys (`sk-ant-api03-`, `sk-ant-admin01-`, any `sk-ant-<name><2 digits>-`), OpenAI `sk-proj-`, `sk-svcacct-` and `sk-admin-` (`openai_key` no longer matches Anthropic keys), GitHub fine-grained tokens (`github_pat_`), AWS temporary keys (`ASIA`), Google API keys (`AIza`) and OAuth client secrets (`GOCSPX-`), Stripe `sk_` and `rk_` live and test keys, Slack webhooks, JWTs, Hugging Face (`hf_`), GitLab (`glpat-`), npm (`npm_`), SendGrid, Twilio (`SK`), Azure storage `AccountKey=`, xAI (`xai-`) and database URLs with an inline password. Overlapping matches keep only the longest span. All new credential types are hard blocks, except JWTs and password assignments, which coach.
- Tests: `tests/test_secrets_formats.py` builds its fake keys at runtime, so no key-shaped literal is committed. Plain `pytest` at the repo root now runs 84 tests (was 39).
- Tried and rejected: int8 dynamic quantization of MiniLM. See `docs/OPTIMIZATION_LOG.md`. The model stays fp32.
- Version is 0.6.0 in `VERSION`, the extension manifest and `/health`.

## 0.5.1 (2026-10-14)
- The accurate profile (MiniLM OR word 3-gram OR TF-IDF for documents) is now the default. The previous setup stays available as `profile = "fast"`. `"default"` is accepted as an alias for `accurate`.
- Unicode cleanup before matching: zero-width characters are stripped, text is NFKC normalized, and common Cyrillic and Greek look-alike letters are mapped to Latin.
- Huge pastes and files: when there are more than 48 windows, half of the embedded windows are chosen by TF-IDF score and half are sampled evenly, so a confidential section at the end of a 1 MB paste or a 1500 paragraph docx is still caught. Pastes over 2 MB characters get HTTP 422.
- `/check_file` (file picker and drag-and-drop) now also accepts plain text and code files. It rejects binary content disguised as text (422), reports password-protected PDFs clearly (422), still checks PDFs that only have an owner password, and returns 415 for images, archives and other types.
- Extension: when the backend is down, pastes fail open and show the toast "Paste Guard is offline, so this paste was not checked". Unreadable files show a toast naming the file and the reason. The service worker treats non-200 `/check` responses as errors. Extension version is now 0.5.1.
- Tests: 24 edge-case tests in `tests/test_edge_cases.py`, plus 13 jsdom tests of the content script in `tests/js/content.test.mjs` run from one pytest test. Plain `pytest` at the repo root runs 39 pytest tests, all passing. `pytest.ini` limits collection to `tests/` and ignores `demo/`.
- Measured on the Techvista VM (1 GB, 1 OCPU) after deploy: a short document paste check takes about 0.10 s end to end with the accurate profile. Service RAM is about 370 MB.

## 0.5.0 (2026-10-13)
- Selectable profiles in `paste-guard.toml` (`profile = "accurate"` or `PG_PROFILE=accurate`). Default unchanged.
- `accurate` profile: MiniLM OR 3-gram OR TF-IDF for documents. Held-out doc F1 0.94 to 0.97, recall 0.90 to 0.94, false alarms 2.8%, /check p95 56 ms.
- Benchmarks extended to bge-large, mxbai-embed-large, gte-large and 3-way hybrids, tuned at a 3% false alarm budget, with an accuracy next to speed table.
- Windows setup script `deploy/windows/setup.ps1`.

## 0.4.0 (2026-10-13)
- Hybrid matching: embedding cosine OR word 3-gram containment. Held-out document F1 0.87 to 0.94 at the same 3% FPR.
- Separated document bands: nudge 0.58, coach 0.64, block 0.74 (were 0.62, 0.63, 0.78). New `[fingerprint]` config.
- Redaction keeps headings and code signatures and replaces bodies with `[REDACTED: matches <source> lines a-b]`.
- Verdict log always records a site (hostname, referer, or `direct API call`).
- Held-out evaluation split by source document, model benchmark across 5 embedding models and 3 lexical baselines
  (`eval/benchmarks.md`, `eval/bench_all.sh`), HTTP latency script, `docs/OPTIMIZATION_LOG.md`.

## 0.3.0 (2026-10-13)
- Confidential document protection: .md, .txt, .pdf and .docx are indexed in paragraph-aware passages at two granularities.
- File uploads and drag-and-drop are checked on protected AI sites; PDF and DOCX text is extracted by the backend (`/check_file`).
- Separate thresholds for documents and code, set in `paste-guard.toml`.
- Overlay shows the matched passage and source document.
- One-command setup (`install.sh` or `docker compose up -d`), `pasteguard` CLI with `reindex`, hot reload of the index.
- Admin page at `/admin` with index stats and a verdict log that stores hashes and lengths only.
- Extension popup with status indicator, settings page with per-site pause, icons.
- Evaluation harness (`eval/run_eval.py`) comparing semantic matching with a regex and keyword baseline.

## 0.2.0
- Real embedding model (all-MiniLM-L6-v2 via fastembed), sqlite-vec index, semantic verdicts, redaction.

## 0.1.0
- Paste hook, overlay, local backend.
