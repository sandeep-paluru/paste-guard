# Paste Guard

[![CI](https://github.com/sandeep-paluru/paste-guard/actions/workflows/ci.yml/badge.svg)](https://github.com/sandeep-paluru/paste-guard/actions/workflows/ci.yml)

Paste Guard is a Chrome extension and a local backend by Sandeep Paluru. It checks text you paste, files you upload, and files you drop into claude.ai, chatgpt.com, and chat.openai.com against an index of your own documents and code.

Keyword and regex rules catch exact phrases and known secret formats. They miss a memo that was reworded, summarized, or cut into pieces. Paste Guard also compares the paste to the index with a small local embedding model, so paraphrases and partial copies can match. The check runs on your machine or your own server. Paste text is not sent anywhere else.

## What you need

Python 3.10 or newer, git, and Chrome. The first run downloads the MiniLM model (about 90 MB) and the Python packages.

## Install and run

macOS and Linux:

```
git clone https://github.com/sandeep-paluru/paste-guard.git
cd paste-guard
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
```

Windows (PowerShell):

```
git clone https://github.com/sandeep-paluru/paste-guard.git
cd paste-guard
py -m venv .venv
.venv\Scripts\pip install -r backend\requirements.txt
```

The sample index uses the documents in `demo/company-docs` (a fictional company, Calloway Metrics). Code matching uses one open source repository as stand-in company code. Documents and the secrets scan work without it. Code matching stays off until the repository is present.

```
git clone https://github.com/pallets/itsdangerous demo/company-repo
git -C demo/company-repo checkout 672971d66a2ef9f85151e53283113f33d642dabd
```

Build the index and start the backend on 127.0.0.1:8765.

macOS and Linux:

```
./pasteguard reindex
./pasteguard serve
```

`./install.sh` creates the virtualenv, installs dependencies, and builds the index. `./install.sh --service` also installs a systemd unit.

Windows (PowerShell), from `backend`:

```
..\.venv\Scripts\python index.py reindex
..\.venv\Scripts\python -m uvicorn app:app --host 127.0.0.1 --port 8765
```

After the first reindex you can start it by double-clicking `deploy\windows\start-backend-with-logs.cmd`. See `deploy/windows/README.md` for the setup script.

Docker: `docker compose up -d` publishes the API on 127.0.0.1:8765. Point the compose volumes at the document and code folders you want indexed.

Open http://127.0.0.1:8765/health to confirm the backend is up.

Load the extension. In Chrome open `chrome://extensions`, turn on Developer mode, click Load unpacked, and pick the `extension/` folder. The toolbar icon shows a green dot when protection is on.

Open http://127.0.0.1:8765/logs to watch checks. Each line has the verdict, scores, and latency. The pasted text is not stored.

The PDFs in `demo/demo-cases/` are there to try by hand. Expected verdicts are in `demo/demo-cases/README.md`.

Use `127.0.0.1`, not `localhost`. On some machines `localhost` resolves to `::1` first, and the backend listens on IPv4 `127.0.0.1` only. The extension defaults to `http://127.0.0.1:8765`. Change that on the extension options page if the backend is elsewhere.

## How it works

The content script on the protected sites catches paste, the file picker, and drag-and-drop. Text files are read in the browser. PDF and DOCX go to the backend, which extracts the text. The service worker posts to `http://127.0.0.1:8765/check` or `/check_file`.

Each check does four things. The worst verdict wins.

1. Secret scan. AWS, Anthropic, OpenAI, GitHub, Stripe, Slack, and other provider keys, private keys, and database URLs that include a password are blocked. The overlay can redact them in one click.
2. Word 3-gram overlap with each indexed passage. This catches verbatim copies and partial excerpts.
3. TF-IDF similarity (word 1-grams and 2-grams) for documents. This catches pastes that share vocabulary.
4. MiniLM embeddings (`sentence-transformers/all-MiniLM-L6-v2`, ONNX on CPU through fastembed), nearest passages in sqlite-vec. This catches rewording that shares little vocabulary.

The 3-gram and TF-IDF checks run first and take a few milliseconds. MiniLM is skipped when those already say block, or when the paste shares almost no vocabulary with the index (best TF-IDF below 0.10). `PG_FAST_PATH=0` turns that off.

Verdicts are allow, nudge, coach, and block. The overlay names the matched document and shows the matching sentences side by side, with shared phrases highlighted.

Nothing is trained. MiniLM is a public pretrained model used as is. The similarity thresholds were tuned on the eval set. More detail is in `docs/ARCHITECTURE.md` and `docs/OPTIMIZATION_LOG.md`.

## Results

The eval set is 472 pastes built from 18 confidential documents and one code repository: verbatim copies, excerpts, paraphrases, summaries, tone rewrites, and unrelated negatives. Held-out means thresholds were tuned on pastes from 9 documents and scored on the other 9, then swapped.

| Documents | Recall | False alarms |
|---|---|---|
| Paste Guard, default `accurate` profile (held-out) | 0.94 | 2.8% |
| Regex and keyword baseline | 0.11 | 0% |

The regex baseline has no thresholds to tune. Its figure is from `eval/results.md`.

Verbatim text and partial excerpts are caught almost always. Paraphrases are caught most of the time. Summaries and tone rewrites land around half. Tables, the other models that were tried, and latency are in `eval/results.md` and `eval/benchmarks.md`.

## Limits

- Summaries and tone rewrites are the weak spot, about 0.50 recall held-out.
- If the backend is down, pastes go through. The page says so.
- On a 2 vCPU, 1 GB VM the p95 latency is over the 100 ms goal, because of memory pressure. A normal laptop is fine.
- Chrome only, and only the sites listed in `paste-guard.toml` (claude.ai, chatgpt.com, chat.openai.com).
- The eval set is synthetic and built around the demo company. Numbers on real documents will differ.

## Configuration

`paste-guard.toml` sets the folders to protect (`[index] docs` and `code`), the server address, thresholds, protected sites, and the profile. `accurate` is the default. `fast` drops TF-IDF. After changing the folders, run `./pasteguard reindex` (on Windows, `python index.py reindex` from `backend`). The running server reloads the new index.

Other pages, local connections only: `/admin` (indexed passages, verdict counts, recent checks; hashes and lengths only), `/demo/compare` (regex baseline next to Paste Guard), and `/demo/redteam` (37 adversarial rewrites replayed through `/check`).

## Tests

The suite needs the sample code repository cloned (the `itsdangerous` checkout above) and an index built with `./pasteguard reindex`. Backend tests use the real model and the real index. The extension tests use node:test and jsdom.

```
.venv/bin/pip install pytest httpx
cd tests/js && npm ci && cd ../..
.venv/bin/python -m pytest
```

On Windows: `.venv\Scripts\python -m pytest`.

`pytest.ini` sets `testpaths = tests`. `tests/test_extension_js.py` runs `node --test` in `tests/js`. If `jsdom` is missing and npm is available, that test installs it first. If node is missing, the JS test is skipped. `npm test` in `tests/js` runs the same `node --test` command.

GitHub Actions runs this on push and pull request to `main` (`.github/workflows/ci.yml`). The workflow caches the model under `~/.cache/paste-guard/models` (`PG_MODEL_CACHE`).

`./pasteguard eval` reruns the evaluation and writes `eval/results.md`.

## Layout

```
backend/        FastAPI server: matching, secret scan, index, /logs, /admin, demo pages
extension/      Chrome extension (Manifest V3): content script, overlay, options, popup
demo/
  company-docs/ documents of the fictional company Calloway Metrics (what gets indexed)
  demo-cases/   PDFs to try by hand, with expected verdicts
  compare/      examples for /demo/compare
  redteam/      adversarial rewrites for /demo/redteam
eval/           eval data, scripts, results, benchmarks
tests/          pytest suite and extension JS tests
docs/           architecture, optimization log, write-up
deploy/windows/ Windows setup and start/stop scripts
install.sh, pasteguard, Dockerfile, docker-compose.yml
paste-guard.toml
```
