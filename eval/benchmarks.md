# Paste Guard benchmarks

Everything on this page was produced by `eval/bench_all.sh` (scoring in `eval/bench_score.py`, report in `eval/bench_report.py`) on CPU, 2 ONNX threads per model, on the same 472 samples as `eval/results.md` (356 document pastes over 18 Calloway Metrics documents, 116 code pastes over one repository).

**No model was trained or fine-tuned.** Every embedding model is a public pretrained checkpoint used zero-shot through fastembed (ONNX). The only values fitted to our data are similarity thresholds (and, for TF-IDF, the IDF weights of the indexed corpus).

**In-sample** = threshold tuned and scored on all samples (best F1 with false positive rate at most 3%). **Held-out** = 2-fold split by source document: thresholds tuned on pastes from 9 documents (code: half the source files) and scored on pastes from the other 9, then swapped. Negatives are split between folds by id. Held-out is the honest estimate of how the tuned thresholds carry over to documents they were never tuned on.

Charts: `bench_f1.png` (F1 in-sample vs held-out), `bench_transforms.png` (recall by transform), `bench_speed.png` (accuracy vs latency and RAM), `bench_fastpath.png` (fast path off vs on, 0.6.0). Decisions taken from these numbers are in `docs/OPTIMIZATION_LOG.md`.

## Documents: accuracy

| Method | Threshold | P (in) | R (in) | F1 (in) | FPR (in) | P (held-out) | R (held-out) | F1 (held-out) | FPR (held-out) |
|---|---|---|---|---|---|---|---|---|---|
| all-MiniLM-L6-v2 | 0.63 | 0.99 | 0.80 | 0.88 | 0.03 | 0.99 | 0.77 | 0.87 | 0.03 |
| bge-small-en-v1.5 | 0.79 | 1.00 | 0.74 | 0.85 | 0.01 | 1.00 | 0.74 | 0.85 | 0.01 |
| bge-base-en-v1.5 | 0.74 | 0.99 | 0.85 | 0.91 | 0.03 | 0.98 | 0.86 | 0.92 | 0.07 |
| bge-large-en-v1.5 | 0.76 | 1.00 | 0.77 | 0.87 | 0.00 | 0.99 | 0.80 | 0.88 | 0.03 |
| mxbai-embed-large-v1 | 0.74 | 0.99 | 0.79 | 0.88 | 0.03 | 0.99 | 0.79 | 0.88 | 0.03 |
| gte-large | 0.91 | 1.00 | 0.76 | 0.86 | 0.01 | 0.99 | 0.80 | 0.89 | 0.03 |
| jina-embeddings-v2-base-code | 0.79 | 0.99 | 0.47 | 0.63 | 0.03 | 0.98 | 0.39 | 0.56 | 0.03 |
| nomic-embed-text-v1.5 | 0.83 | 0.99 | 0.70 | 0.82 | 0.03 | 0.98 | 0.71 | 0.82 | 0.06 |
| TF-IDF cosine (1-2 grams) | 0.22 | 1.00 | 0.90 | 0.95 | 0.01 | 1.00 | 0.90 | 0.95 | 0.01 |
| Word 3-gram containment | 0.14 | 1.00 | 0.76 | 0.86 | 0.00 | 1.00 | 0.76 | 0.86 | 0.00 |
| MinHash Jaccard (128 perms) | 0.05 | 1.00 | 0.74 | 0.85 | 0.01 | 1.00 | 0.74 | 0.85 | 0.01 |
| Hybrid: MiniLM OR 3-gram containment | 0.63 / 0.14 | 0.99 | 0.91 | 0.95 | 0.03 | 0.99 | 0.90 | 0.94 | 0.03 |
| Hybrid: MiniLM OR TF-IDF | 0.63 / 0.23 | 0.99 | 0.95 | 0.97 | 0.03 | 0.99 | 0.94 | 0.96 | 0.04 |
| Hybrid: bge-base OR 3-gram | 0.74 / 0.14 | 0.99 | 0.93 | 0.96 | 0.03 | 0.98 | 0.94 | 0.96 | 0.07 |
| Hybrid: bge-base OR TF-IDF | 0.74 / 0.23 | 0.99 | 0.96 | 0.98 | 0.03 | 0.98 | 0.96 | 0.97 | 0.08 |
| Hybrid: bge-large OR 3-gram | 0.76 / 0.14 | 1.00 | 0.89 | 0.94 | 0.00 | 0.99 | 0.90 | 0.94 | 0.03 |
| Hybrid: mxbai-large OR 3-gram | 0.74 / 0.14 | 0.99 | 0.90 | 0.94 | 0.03 | 1.00 | 0.89 | 0.94 | 0.01 |
| Hybrid: MiniLM OR 3-gram OR TF-IDF | 0.63 / 0.15 / 0.23 | 0.99 | 0.95 | 0.97 | 0.03 | 0.99 | 0.94 | 0.97 | 0.03 |
| Hybrid: bge-base OR 3-gram OR TF-IDF | 0.75 / 0.15 / 0.23 | 0.99 | 0.96 | 0.97 | 0.03 | 0.98 | 0.96 | 0.97 | 0.08 |
| Hybrid: bge-large OR 3-gram OR TF-IDF | 0.77 / 0.15 / 0.23 | 1.00 | 0.94 | 0.97 | 0.00 | 0.99 | 0.95 | 0.97 | 0.03 |
| Hybrid: mxbai-large OR 3-gram OR TF-IDF | 0.75 / 0.15 / 0.23 | 1.00 | 0.95 | 0.97 | 0.00 | 0.99 | 0.95 | 0.97 | 0.03 |
| Hybrid: gte-large OR 3-gram OR TF-IDF | 0.91 / 0.15 / 0.23 | 1.00 | 0.95 | 0.97 | 0.01 | 0.99 | 0.95 | 0.97 | 0.03 |
| Regex and keyword DLP | n/a | 1.00 | 0.11 | 0.20 | 0.00 | 1.00 | 0.11 | 0.20 | 0.00 |

## Code: accuracy

| Method | Threshold | P (in) | R (in) | F1 (in) | FPR (in) | P (held-out) | R (held-out) | F1 (held-out) | FPR (held-out) |
|---|---|---|---|---|---|---|---|---|---|
| all-MiniLM-L6-v2 | 0.68 | 1.00 | 0.92 | 0.96 | 0.00 | 0.97 | 1.00 | 0.99 | 0.04 |
| bge-small-en-v1.5 | 0.82 | 0.98 | 0.89 | 0.94 | 0.02 | 0.94 | 0.89 | 0.91 | 0.08 |
| bge-base-en-v1.5 | 0.80 | 0.98 | 0.82 | 0.89 | 0.02 | 0.95 | 0.82 | 0.88 | 0.06 |
| bge-large-en-v1.5 | 0.79 | 1.00 | 0.85 | 0.92 | 0.00 | 0.94 | 0.92 | 0.93 | 0.08 |
| mxbai-embed-large-v1 | 0.80 | 0.98 | 0.83 | 0.90 | 0.02 | 0.97 | 0.85 | 0.90 | 0.04 |
| gte-large | 0.90 | 0.98 | 0.85 | 0.91 | 0.02 | 0.97 | 0.86 | 0.91 | 0.04 |
| jina-embeddings-v2-base-code | 0.81 | 1.00 | 0.55 | 0.71 | 0.00 | 0.96 | 0.77 | 0.86 | 0.04 |
| nomic-embed-text-v1.5 | 0.80 | 0.98 | 0.92 | 0.95 | 0.02 | 0.97 | 0.92 | 0.95 | 0.04 |
| TF-IDF cosine (1-2 grams) | 0.26 | 1.00 | 1.00 | 1.00 | 0.00 | 0.97 | 1.00 | 0.99 | 0.04 |
| Word 3-gram containment | 0.13 | 1.00 | 0.98 | 0.99 | 0.00 | 0.98 | 0.98 | 0.98 | 0.02 |
| MinHash Jaccard (128 perms) | 0.05 | 1.00 | 0.95 | 0.98 | 0.00 | 1.00 | 0.95 | 0.98 | 0.00 |
| Hybrid: MiniLM OR 3-gram containment | 0.68 / 0.13 | 1.00 | 1.00 | 1.00 | 0.00 | 0.96 | 1.00 | 0.98 | 0.06 |
| Hybrid: MiniLM OR TF-IDF | 0.68 / 0.26 | 1.00 | 1.00 | 1.00 | 0.00 | 0.96 | 1.00 | 0.98 | 0.06 |
| Hybrid: bge-base OR 3-gram | 0.80 / 0.13 | 0.99 | 1.00 | 0.99 | 0.02 | 0.94 | 1.00 | 0.97 | 0.08 |
| Hybrid: bge-base OR TF-IDF | 0.82 / 0.26 | 1.00 | 1.00 | 1.00 | 0.00 | 0.94 | 1.00 | 0.97 | 0.08 |
| Hybrid: bge-large OR 3-gram | 0.79 / 0.13 | 1.00 | 1.00 | 1.00 | 0.00 | 0.93 | 1.00 | 0.96 | 0.10 |
| Hybrid: mxbai-large OR 3-gram | 0.81 / 0.13 | 1.00 | 1.00 | 1.00 | 0.00 | 0.96 | 1.00 | 0.98 | 0.06 |
| Hybrid: MiniLM OR 3-gram OR TF-IDF | 0.69 / 0.13 / 0.27 | 1.00 | 1.00 | 1.00 | 0.00 | 0.96 | 1.00 | 0.98 | 0.06 |
| Hybrid: bge-base OR 3-gram OR TF-IDF | 0.83 / 0.13 / 0.27 | 1.00 | 1.00 | 1.00 | 0.00 | 0.94 | 1.00 | 0.97 | 0.08 |
| Hybrid: bge-large OR 3-gram OR TF-IDF | 0.79 / 0.13 / 0.27 | 1.00 | 1.00 | 1.00 | 0.00 | 0.93 | 1.00 | 0.96 | 0.10 |
| Hybrid: mxbai-large OR 3-gram OR TF-IDF | 0.81 / 0.13 / 0.27 | 1.00 | 1.00 | 1.00 | 0.00 | 0.96 | 1.00 | 0.98 | 0.06 |
| Hybrid: gte-large OR 3-gram OR TF-IDF | 0.91 / 0.13 / 0.27 | 1.00 | 1.00 | 1.00 | 0.00 | 0.96 | 1.00 | 0.98 | 0.06 |
| Regex and keyword DLP | n/a | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |

## Chunking ablation (MiniLM, documents)

Same model and paste windows, different ways of cutting the documents into indexed passages.

| Index | Doc passages | F1 (in) | R (in) | R at fixed 0.63 | F1 (held-out) | R (held-out) |
|---|---|---|---|---|---|---|
| MiniLM, 120-200 word chunks only (v0.3 before short passages) | 124 | 0.81 | 0.69 | 0.51 | 0.81 | 0.69 |
| MiniLM, pre-fix splitter (duplicated overlap) | 533 | 0.84 | 0.73 | 0.81 | 0.85 | 0.76 |
| MiniLM, long chunks + 60 word passages (current) | 485 | 0.88 | 0.80 | 0.80 | 0.87 | 0.77 |

## Detection per transform (held-out thresholds)

Positives: share detected. Negatives: share falsely flagged.

| Kind | Transform | N | all-MiniLM-L6-v2 | bge-small-en-v1.5 | bge-base-en-v1.5 | bge-large-en-v1.5 | mxbai-embed-large-v1 | gte-large | jina-embeddings-v2-base-code | nomic-embed-text-v1.5 | TF-IDF cosine (1-2 grams) | Word 3-gram containment | MinHash Jaccard (128 perms) | Hybrid: MiniLM OR 3-gram containment | Hybrid: MiniLM OR TF-IDF | Hybrid: bge-base OR 3-gram | Hybrid: bge-base OR TF-IDF | Hybrid: bge-large OR 3-gram | Hybrid: mxbai-large OR 3-gram | Hybrid: MiniLM OR 3-gram OR TF-IDF | Hybrid: bge-base OR 3-gram OR TF-IDF | Hybrid: bge-large OR 3-gram OR TF-IDF | Hybrid: mxbai-large OR 3-gram OR TF-IDF | Hybrid: gte-large OR 3-gram OR TF-IDF | Regex and keyword DLP |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| code | partial | 11 | 1.00 | 0.91 | 0.73 | 1.00 | 0.91 | 0.91 | 0.91 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 |
| code | public_code (negative) | 25 | 0.04 | 0.08 | 0.04 | 0.08 | 0.04 | 0.04 | 0.04 | 0.04 | 0.08 | 0.04 | 0.00 | 0.08 | 0.08 | 0.08 | 0.08 | 0.12 | 0.08 | 0.08 | 0.08 | 0.12 | 0.08 | 0.08 | 0.00 |
| code | reformat | 11 | 1.00 | 1.00 | 0.91 | 1.00 | 0.91 | 0.91 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 |
| code | rename | 11 | 1.00 | 0.73 | 0.73 | 0.91 | 0.73 | 0.73 | 0.73 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 |
| code | rename+reformat | 11 | 1.00 | 0.82 | 0.82 | 0.82 | 0.82 | 0.82 | 0.73 | 0.82 | 1.00 | 1.00 | 0.82 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 |
| code | verbatim | 11 | 1.00 | 1.00 | 0.91 | 0.91 | 0.91 | 0.91 | 0.91 | 0.91 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 |
| code | wrapped | 11 | 1.00 | 0.91 | 0.82 | 0.91 | 0.82 | 0.91 | 0.36 | 0.82 | 1.00 | 0.91 | 0.91 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 |
| code | wrapped_public_code (negative) | 25 | 0.04 | 0.08 | 0.08 | 0.08 | 0.04 | 0.04 | 0.04 | 0.04 | 0.00 | 0.00 | 0.00 | 0.04 | 0.04 | 0.08 | 0.08 | 0.08 | 0.04 | 0.04 | 0.08 | 0.08 | 0.04 | 0.04 | 0.00 |
| doc | paraphrase | 36 | 0.78 | 0.28 | 0.72 | 0.44 | 0.47 | 0.81 | 0.19 | 0.61 | 0.89 | 0.39 | 0.28 | 0.89 | 0.94 | 0.86 | 0.92 | 0.67 | 0.64 | 0.97 | 0.92 | 0.89 | 0.92 | 0.94 | 0.03 |
| doc | partial_excerpt | 51 | 0.55 | 0.59 | 0.75 | 0.65 | 0.65 | 0.67 | 0.16 | 0.57 | 1.00 | 0.92 | 0.92 | 0.92 | 1.00 | 0.94 | 1.00 | 0.94 | 0.94 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.10 |
| doc | public_text (negative) | 36 | 0.03 | 0.00 | 0.00 | 0.00 | 0.03 | 0.06 | 0.00 | 0.08 | 0.03 | 0.00 | 0.03 | 0.03 | 0.06 | 0.00 | 0.03 | 0.00 | 0.03 | 0.03 | 0.03 | 0.00 | 0.03 | 0.03 | 0.00 |
| doc | reordered_bullets | 29 | 0.97 | 0.86 | 0.93 | 0.93 | 0.90 | 0.83 | 0.86 | 0.86 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.10 |
| doc | summary | 18 | 0.50 | 0.67 | 0.83 | 0.72 | 0.72 | 0.83 | 0.28 | 0.33 | 0.28 | 0.00 | 0.06 | 0.50 | 0.56 | 0.83 | 0.83 | 0.72 | 0.72 | 0.56 | 0.78 | 0.72 | 0.78 | 0.72 | 0.22 |
| doc | tone_rewrite | 18 | 0.44 | 0.61 | 0.61 | 0.61 | 0.56 | 0.56 | 0.17 | 0.33 | 0.61 | 0.22 | 0.22 | 0.50 | 0.72 | 0.72 | 0.83 | 0.67 | 0.67 | 0.72 | 0.83 | 0.78 | 0.78 | 0.78 | 0.00 |
| doc | verbatim | 51 | 0.94 | 0.98 | 0.98 | 0.98 | 1.00 | 0.94 | 0.51 | 0.94 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.14 |
| doc | wrapped_paraphrase | 18 | 0.72 | 0.67 | 0.89 | 0.83 | 0.78 | 0.78 | 0.22 | 0.56 | 0.78 | 0.39 | 0.33 | 0.83 | 0.89 | 0.94 | 0.94 | 0.89 | 0.78 | 0.83 | 0.94 | 0.89 | 0.83 | 0.83 | 0.00 |
| doc | wrapped_prompt | 63 | 0.92 | 0.95 | 0.98 | 0.97 | 0.95 | 0.86 | 0.52 | 0.87 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.19 |
| doc | wrapped_public_text (negative) | 36 | 0.03 | 0.03 | 0.14 | 0.06 | 0.03 | 0.00 | 0.06 | 0.03 | 0.00 | 0.00 | 0.00 | 0.03 | 0.03 | 0.14 | 0.14 | 0.06 | 0.00 | 0.03 | 0.14 | 0.06 | 0.03 | 0.03 | 0.00 |

## Source attribution

For detected document positives (held-out), how often the top hit is the right document.

| Method | Correct source |
|---|---|
| all-MiniLM-L6-v2 | 95% of 220 |
| bge-small-en-v1.5 | 97% of 210 |
| bge-base-en-v1.5 | 93% of 245 |
| bge-large-en-v1.5 | 96% of 226 |
| mxbai-embed-large-v1 | 99% of 224 |
| gte-large | 97% of 228 |
| jina-embeddings-v2-base-code | 87% of 111 |
| nomic-embed-text-v1.5 | 98% of 201 |
| TF-IDF cosine (1-2 grams) | 100% of 256 |
| Word 3-gram containment | 99% of 215 |
| MinHash Jaccard (128 perms) | 100% of 211 |
| Hybrid: MiniLM OR 3-gram containment | 93% of 255 |

## Speed and footprint (this box, CPU)

Latency is one full check: cut the paste into windows, embed them, search all indexed chunks. Index build = embedding all 594 chunks (485 document passages, 109 code chunks). RSS = peak resident memory of the scoring process with model and index loaded.

| Method | Dims | Model on disk | Load | Index build | p50 per check | p95 per check | Peak RSS |
|---|---|---|---|---|---|---|---|
| all-MiniLM-L6-v2 | 384 | 91 MB | 0.4 s | 18.0 s | 9 ms | 65 ms | 493 MB |
| bge-small-en-v1.5 | 384 | 67 MB | 0.6 s | 65.8 s | 20 ms | 144 ms | 798 MB |
| bge-base-en-v1.5 | 768 | 219 MB | 1.1 s | 253.9 s | 65 ms | 474 ms | 1413 MB |
| bge-large-en-v1.5 | 1024 | 1338 MB | 8.7 s | 728.0 s | 196 ms | 1159 ms | 3931 MB |
| mxbai-embed-large-v1 | 1024 | 1338 MB | 10.3 s | 626.9 s | 192 ms | 1305 ms | 3790 MB |
| gte-large | 1024 | 1338 MB | 10.1 s | 580.6 s | 212 ms | 1339 ms | 4041 MB |
| jina-embeddings-v2-base-code | 768 | 644 MB | 3.2 s | 180.3 s | 75 ms | 433 ms | 1927 MB |
| nomic-embed-text-v1.5 | 768 | 548 MB | 2.3 s | 343.5 s | 87 ms | 590 ms | 3258 MB |
| TF-IDF cosine (1-2 grams) | - | - | 0.0 s | 0.9 s | 1 ms | 2 ms | 138 MB |
| Word 3-gram containment | - | - | 0.0 s | 0.1 s | 1 ms | 2 ms | 67 MB |
| MinHash Jaccard (128 perms) | - | - | 0.0 s | 0.1 s | 0 ms | 1 ms | 67 MB |

Deployed model on the Techvista VM (techvista-vm, 2 vCPU, 0.9 GB RAM): 80 real `/check` calls over HTTP on the VM itself (hybrid matching, PG_THREADS=1, VM shared with the existing Techvista services), p50 208 ms, p95 995 ms, backend RSS 203 MB. The VM is short on memory and pages part of the process out, which is what drives the p95.

Same HTTP test against the backend on this box (8 vCPU): p50 16 ms, p95 58 ms, backend RSS 280 MB.

## Accuracy next to speed (documents, held-out)

Hard requirement: full check p95 under 100 ms on a normal CPU, false alarms at most 3%. Latency of a hybrid = sum of its parts (scoring only, this box, 2 threads); the HTTP rows below include the whole /check request.

| Config | F1 | Recall | Precision | False alarms | Summary recall | Tone rewrite recall | p50 | p95 | Meets both? |
|---|---|---|---|---|---|---|---|---|---|
| all-MiniLM-L6-v2 | 0.870 | 0.77 | 0.99 | 2.8% | 0.50 | 0.44 | 9 ms | 65 ms | yes |
| bge-small-en-v1.5 | 0.848 | 0.74 | 1.00 | 1.4% | 0.67 | 0.61 | 20 ms | 144 ms | no |
| bge-base-en-v1.5 | 0.918 | 0.86 | 0.98 | 6.9% | 0.83 | 0.61 | 65 ms | 474 ms | no |
| bge-large-en-v1.5 | 0.883 | 0.80 | 0.99 | 2.8% | 0.72 | 0.61 | 196 ms | 1159 ms | no |
| mxbai-embed-large-v1 | 0.878 | 0.79 | 0.99 | 2.8% | 0.72 | 0.56 | 192 ms | 1305 ms | no |
| gte-large | 0.887 | 0.80 | 0.99 | 2.8% | 0.83 | 0.56 | 212 ms | 1339 ms | no |
| jina-embeddings-v2-base-code | 0.559 | 0.39 | 0.98 | 2.8% | 0.28 | 0.17 | 75 ms | 433 ms | no |
| nomic-embed-text-v1.5 | 0.822 | 0.71 | 0.98 | 5.6% | 0.33 | 0.33 | 87 ms | 590 ms | no |
| TF-IDF cosine (1-2 grams) | 0.946 | 0.90 | 1.00 | 1.4% | 0.28 | 0.61 | 1 ms | 2 ms | yes |
| Word 3-gram containment | 0.862 | 0.76 | 1.00 | 0.0% | 0.00 | 0.22 | 1 ms | 2 ms | yes |
| MinHash Jaccard (128 perms) | 0.851 | 0.74 | 1.00 | 1.4% | 0.06 | 0.22 | 0 ms | 1 ms | yes |
| Hybrid: MiniLM OR 3-gram containment | 0.943 | 0.90 | 0.99 | 2.8% | 0.50 | 0.50 | 9 ms | 67 ms | yes |
| Hybrid: MiniLM OR TF-IDF | 0.964 | 0.94 | 0.99 | 4.2% | 0.56 | 0.72 | 10 ms | 66 ms | no |
| Hybrid: bge-base OR 3-gram | 0.960 | 0.94 | 0.98 | 6.9% | 0.83 | 0.72 | 66 ms | 477 ms | no |
| Hybrid: bge-base OR TF-IDF | 0.972 | 0.96 | 0.98 | 8.3% | 0.83 | 0.83 | 66 ms | 476 ms | no |
| Hybrid: bge-large OR 3-gram | 0.945 | 0.90 | 0.99 | 2.8% | 0.72 | 0.67 | 196 ms | 1162 ms | no |
| Hybrid: mxbai-large OR 3-gram | 0.941 | 0.89 | 1.00 | 1.4% | 0.72 | 0.67 | 193 ms | 1308 ms | no |
| Hybrid: MiniLM OR 3-gram OR TF-IDF | 0.966 | 0.94 | 0.99 | 2.8% | 0.56 | 0.72 | 10 ms | 69 ms | yes |
| Hybrid: bge-base OR 3-gram OR TF-IDF | 0.970 | 0.96 | 0.98 | 8.3% | 0.78 | 0.83 | 67 ms | 478 ms | no |
| Hybrid: bge-large OR 3-gram OR TF-IDF | 0.969 | 0.95 | 0.99 | 2.8% | 0.72 | 0.78 | 197 ms | 1163 ms | no |
| Hybrid: mxbai-large OR 3-gram OR TF-IDF | 0.971 | 0.95 | 0.99 | 2.8% | 0.78 | 0.78 | 194 ms | 1309 ms | no |
| Hybrid: gte-large OR 3-gram OR TF-IDF | 0.971 | 0.95 | 0.99 | 2.8% | 0.72 | 0.78 | 213 ms | 1343 ms | no |

Accurate profile (MiniLM OR 3-gram OR TF-IDF), 120 real `/check` calls over HTTP on this box (8 vCPU, PG_THREADS=2): p50 19 ms, p95 56 ms, backend RSS 379 MB.

## Two-step fast path (0.6.0)

Produced by `eval/fastpath_eval.py`, which runs `app.decide()` on all 472 eval pastes with the fast path off and on (`eval/bench/fastpath.json`). Deployed thresholds, flagged = coach or block verdict. Timings are in-process backend logic on this box (8 cores). The fast path runs 3-gram containment and TF-IDF first and skips MiniLM when a cheap check already reaches block, or when the best TF-IDF score against any indexed passage is below 0.10 (`[fast_path] skip_below`, `PG_FAST_PATH=0` turns it off). 0.10 was chosen because no positive with a MiniLM score of 0.60 or more has TF-IDF below 0.12, in either held-out fold.

| Set | Recall off | Recall on | False alarms off | False alarms on | p50 off | p50 on | p95 off | p95 on |
|---|---|---|---|---|---|---|---|---|
| All 472 pastes | 0.946 | 0.946 | 2.5% | 2.5% | 11.0 ms | 3.6 ms | 70.1 ms | 21.9 ms |
| Documents | 0.933 | 0.933 | 1.4% | 1.4% | 9.8 ms | 3.3 ms | 44.0 ms | 16.2 ms |
| Code | 1.00 | 1.00 | 4% (2 of 50) | 4% (2 of 50) | 17.6 ms | 5.2 ms | 132.3 ms | 46.7 ms |

MiniLM was skipped on 58.5% of the eval pastes. One verdict changed out of 472: a negative went from nudge to allow (nudge is not a flag). Per held-out fold, recall and false alarm rate are identical off and on: document fold A recall 0.939, FPR 0.0; fold B recall 0.927, FPR 2.7%. The code false alarm rate of 4% is unchanged from 0.5.1 and is a known limit.

![Fast path off vs on: latency and accuracy](bench_fastpath.png)

The eval set is mostly near-matches, so in daily use, where most pastes are unrelated text, the skip rate should be higher. I did not measure that.

Real `/check` calls over HTTP (`eval/http_latency.py`):

| Machine | 0.5.1 p50 | 0.5.1 p95 | 0.6.0 p50 | 0.6.0 p95 | File |
|---|---|---|---|---|---|
| This box (8 CPU, 15.6 GB) | 19.1 ms | 56.1 ms | 7.3 ms | 22.5 ms | `eval/bench/box_latency_0.6.json` |
| Techvista VM (2 CPU, 0.9 GB RAM, shared, PG_THREADS=1) | 130.6 ms | 801.9 ms | 84.0 ms | 397.2 ms | `eval/bench/vm_latency_0.6.json` |

The VM tail is memory pressure and swap, not the model.

Cold start (first `/check` after a restart, with the 0.6.0 warm-up at startup): box 1.29 s to 0.024 s, with startup itself going from 0.45 s to 1.75 s; VM about 8.5 s to 0.18 s, with an 18 s warm-up at startup.

Rejected: int8 dynamic quantization of MiniLM. The model went from 90.4 MB to 22.9 MB and 6.6 ms to 3.9 ms per text, but cosine to the fp32 vectors averaged 0.952 and fell to 0.888 on 120 doc pastes, more than the gap between the coach and block bands. fp32 stays.
