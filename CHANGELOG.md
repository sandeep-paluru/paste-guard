# Changelog

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
