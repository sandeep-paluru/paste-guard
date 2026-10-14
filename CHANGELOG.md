# Changelog

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
