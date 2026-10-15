# Paste Guard

Paste Guard is a proof of concept I built for Sidekick Labs. It stops confidential company documents, source code
and secrets from being pasted or uploaded into AI chat tools like ChatGPT and Claude. Keyword and regex DLP rules
only catch exact phrases, so a memo that has been reworded, summarized or cut into pieces goes straight through.
Paste Guard compares every paste, file upload and drag-and-drop against an index of your own documents and code
using a small local embedding model, so it also catches paraphrases and partial copies. Everything runs on your
machine or your own server; no text is sent anywhere else.

## Quick start (Windows, macOS, Linux)

You need Python 3.10 or newer, git and Chrome. The first run downloads about 90 MB (the MiniLM model) and Python packages.

**1. Get the code and install**

macOS / Linux:
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

**2. (Optional) fetch the sample code repository.** The demo protects one open source project as stand-in company code.
Skip this and code matching is simply off; documents and secrets still work.
```
git clone https://github.com/pallets/itsdangerous demo/company-repo
git -C demo/company-repo checkout 672971d66a2ef9f85151e53283113f33d642dabd
```

**3. Build the index and start the backend on 127.0.0.1:8765**

macOS / Linux:
```
./pasteguard reindex
./pasteguard serve
```

Windows (PowerShell):
```
cd backend
..\.venv\Scripts\python index.py reindex
..\.venv\Scripts\python -m uvicorn app:app --host 127.0.0.1 --port 8765
```
After the first reindex you can also start it by double-clicking `deploy\windows\start-backend-with-logs.cmd`.

Check it is up: open http://127.0.0.1:8765/health in a browser.

**4. Load the extension.** In Chrome open `chrome://extensions`, turn on Developer mode, click **Load unpacked** and
pick the `extension/` folder. The toolbar icon shows a green dot when protection is on.

**5. Watch the live log.** Open http://127.0.0.1:8765/logs. Every check shows up there with its verdict, scores and
latency (never the pasted text).

**6. Try the demo cases.** Open claude.ai or chatgpt.com and paste text from, or drop, the PDFs in
`demo/demo-cases/`. The expected verdict for each one is in `demo/demo-cases/README.md`.

Use `127.0.0.1`, not `localhost`. On some machines `localhost` resolves to the IPv6 address `::1` first, while the backend
only listens on IPv4 `127.0.0.1`. The extension defaults to
`http://127.0.0.1:8765`; you can change it on the extension's options page.

## How it works

```
 Chrome extension                          Paste Guard backend (FastAPI, local)
 paste / file picker / drag-and-drop  ->   /check (text) or /check_file (PDF, DOCX, text, code)
                                           1. secret scan (API keys, private keys, DB URLs)
                                           2. word 3-gram overlap with each indexed passage
                                           3. TF-IDF similarity
                                           4. MiniLM embedding, nearest passages in sqlite-vec
 overlay: allow / nudge / coach / block <- worst verdict wins, plus matched source and redacted text
```

- **Secrets** (AWS, Anthropic, OpenAI, GitHub, Stripe, Slack and many more, private keys, database URLs with a password)
  are always blocked and can be redacted with one click.
- **3-gram overlap** catches verbatim copies and partial excerpts. **TF-IDF** catches pastes that share vocabulary.
  **MiniLM** (all-MiniLM-L6-v2, ONNX on CPU) catches rewording that shares neither.
- Each check gives its own verdict and the **worst one wins**.
- **Fast path:** 3-gram and TF-IDF run first and take a few ms. MiniLM is skipped when they already say block, or when
  the paste shares almost no vocabulary with any indexed passage (best TF-IDF below 0.10).
- The overlay shows which document matched and why: the matching sentences side by side with shared phrases highlighted.

Nothing is trained. MiniLM is a public pretrained model used as is; only the similarity thresholds were tuned on the eval data.
More detail: `docs/ARCHITECTURE.md`, `docs/OPTIMIZATION_LOG.md`.

## Results

Evaluated on 472 pastes built from 18 confidential documents and one code repository (verbatim copies, excerpts,
paraphrases, summaries, tone rewrites, plus unrelated negatives). Held-out means thresholds were tuned on pastes from
9 documents and scored on the other 9, then swapped, so these numbers are not tuned on the data they report.

| Documents | Recall | False alarms |
|---|---|---|
| Paste Guard, default `accurate` profile (held-out) | 0.94 | 2.8% |
| Regex and keyword baseline | 0.11 | 0% |

The regex baseline has no thresholds to tune, so its figure comes straight from `eval/results.md`.

Per transform (held-out): verbatim and partial excerpts are caught almost always, paraphrases mostly, summaries and
tone rewrites about half the time. Full tables, every model tried, and latency: `eval/results.md` and `eval/benchmarks.md`.

## Known gaps

- **Summaries and tone rewrites** are the weak spot, at about 0.50 recall held-out.
- **Code dropped as a file:** `Signing Module Review` gets coach when its text is pasted, but not when the PDF is dropped.
- **Fail-open:** if the backend is down, pastes go through unchecked (the page says so).
- **Slow small VMs:** on a 2 vCPU, 1 GB VM the p95 latency goal of 100 ms is not met because of memory pressure. A normal laptop is fine.
- **Chrome only**, and only the sites listed in `paste-guard.toml` (claude.ai, chatgpt.com, chat.openai.com).
- The eval set is synthetic and built around the demo company; real-world numbers will differ.

## Configuration

`paste-guard.toml` sets the folders to protect (`[index] docs` and `code`), the server address, thresholds, protected
sites and the profile (`accurate` by default, or `fast`, which drops TF-IDF). After changing the folders run
`./pasteguard reindex` (Windows: `python index.py reindex` from `backend\`). The running server picks up the new index.

Other pages on the backend (local connections only): `/admin` (indexed passages, verdict counts, recent checks;
stores hashes and lengths only), `/demo/compare` (regex baseline vs Paste Guard) and `/demo/redteam` (37 pre-generated
adversarial rewrites replayed through `/check`).

## Tests

```
.venv/bin/pip install pytest httpx
.venv/bin/python -m pytest        # Windows: .venv\Scripts\python -m pytest
```
Runs the backend tests against the real model and index, plus the extension's jsdom tests (needs node; skipped if missing).

## Repo layout

```
backend/        FastAPI server: matching, secret scan, index, /logs, /admin and demo pages
extension/      Chrome extension (Manifest V3): content script, overlay, options and popup
demo/
  company-docs/ confidential documents of the fictional company Calloway Metrics (what gets indexed)
  demo-cases/   PDFs to try by hand, with expected verdicts
  compare/      examples for /demo/compare
  redteam/      adversarial rewrites for /demo/redteam
eval/           eval data, scripts, results.md and benchmarks.md
tests/          pytest suite and extension JS tests
docs/           architecture, optimization log and write-up
deploy/windows/ Windows setup and start/stop scripts
install.sh, pasteguard, Dockerfile, docker-compose.yml   setup and run helpers for Linux and macOS
paste-guard.toml  configuration
```
