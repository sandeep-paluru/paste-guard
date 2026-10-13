#!/usr/bin/env bash
# Run every matching method in its own process (clean RAM numbers), then aggregate.
set -e
cd "$(dirname "$0")/.."
PY=${PY:-.venv/bin/python}
for m in ngram minhash tfidf minilm bge-small bge-base bge-large mxbai-large gte-large arctic-l mpnet-para jina-code nomic; do $PY eval/bench_score.py --method $m; done
$PY eval/bench_score.py --method minilm --chunking long_only
$PY eval/bench_score.py --method minilm --chunking bugged_split
$PY eval/bench_report.py
