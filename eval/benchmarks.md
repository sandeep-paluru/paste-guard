# Paste Guard benchmarks

Everything on this page was produced by `eval/bench_all.sh` (scoring in `eval/bench_score.py`, report in `eval/bench_report.py`) on CPU, 2 ONNX threads per model, on the same 472 samples as `eval/results.md` (356 document pastes over 18 Calloway Metrics documents, 116 code pastes over one repository).

**No model was trained or fine-tuned.** Every embedding model is a public pretrained checkpoint used zero-shot through fastembed (ONNX). The only values fitted to our data are similarity thresholds (and, for TF-IDF, the IDF weights of the indexed corpus).

**In-sample** = threshold tuned and scored on all samples (best F1 with false positive rate at most 5%). **Held-out** = 2-fold split by source document: thresholds tuned on pastes from 9 documents (code: half the source files) and scored on pastes from the other 9, then swapped. Negatives are split between folds by id. Held-out is the honest estimate of how the tuned thresholds carry over to documents they were never tuned on.

Charts: `bench_f1.png` (F1 in-sample vs held-out), `bench_transforms.png` (recall by transform), `bench_speed.png` (accuracy vs latency and RAM). Decisions taken from these numbers are in `docs/OPTIMIZATION_LOG.md`.

## Documents: accuracy

| Method | Threshold | P (in) | R (in) | F1 (in) | FPR (in) | P (held-out) | R (held-out) | F1 (held-out) | FPR (held-out) |
|---|---|---|---|---|---|---|---|---|---|
| all-MiniLM-L6-v2 | 0.63 | 0.99 | 0.80 | 0.88 | 0.03 | 0.99 | 0.77 | 0.87 | 0.03 |
| bge-small-en-v1.5 | 0.79 | 1.00 | 0.74 | 0.85 | 0.01 | 1.00 | 0.74 | 0.85 | 0.01 |
| bge-base-en-v1.5 | 0.74 | 0.99 | 0.85 | 0.91 | 0.03 | 0.98 | 0.86 | 0.92 | 0.07 |
| jina-embeddings-v2-base-code | 0.79 | 0.99 | 0.47 | 0.63 | 0.03 | 0.98 | 0.39 | 0.56 | 0.03 |
| nomic-embed-text-v1.5 | 0.83 | 0.99 | 0.70 | 0.82 | 0.03 | 0.98 | 0.71 | 0.82 | 0.06 |
| TF-IDF cosine (1-2 grams) | 0.21 | 0.99 | 0.92 | 0.95 | 0.04 | 1.00 | 0.90 | 0.95 | 0.01 |
| Word 3-gram containment | 0.14 | 1.00 | 0.76 | 0.86 | 0.00 | 1.00 | 0.76 | 0.86 | 0.00 |
| MinHash Jaccard (128 perms) | 0.05 | 1.00 | 0.74 | 0.85 | 0.01 | 1.00 | 0.74 | 0.85 | 0.01 |
| Hybrid: MiniLM OR 3-gram containment | 0.63 / 0.14 | 0.99 | 0.91 | 0.95 | 0.03 | 0.99 | 0.90 | 0.94 | 0.03 |
| Hybrid: MiniLM OR TF-IDF | 0.63 / 0.22 | 0.99 | 0.95 | 0.97 | 0.04 | 0.99 | 0.94 | 0.96 | 0.04 |
| Regex and keyword DLP | n/a | 1.00 | 0.11 | 0.20 | 0.00 | 1.00 | 0.11 | 0.20 | 0.00 |

## Code: accuracy

| Method | Threshold | P (in) | R (in) | F1 (in) | FPR (in) | P (held-out) | R (held-out) | F1 (held-out) | FPR (held-out) |
|---|---|---|---|---|---|---|---|---|---|
| all-MiniLM-L6-v2 | 0.51 | 0.97 | 1.00 | 0.99 | 0.04 | 0.97 | 1.00 | 0.99 | 0.04 |
| bge-small-en-v1.5 | 0.82 | 0.98 | 0.89 | 0.94 | 0.02 | 0.94 | 0.92 | 0.93 | 0.08 |
| bge-base-en-v1.5 | 0.79 | 0.96 | 0.83 | 0.89 | 0.04 | 0.90 | 0.91 | 0.90 | 0.14 |
| jina-embeddings-v2-base-code | 0.59 | 0.97 | 0.95 | 0.96 | 0.04 | 0.96 | 0.77 | 0.86 | 0.04 |
| nomic-embed-text-v1.5 | 0.77 | 0.97 | 0.94 | 0.95 | 0.04 | 0.93 | 0.97 | 0.95 | 0.10 |
| TF-IDF cosine (1-2 grams) | 0.26 | 1.00 | 1.00 | 1.00 | 0.00 | 0.97 | 1.00 | 0.99 | 0.04 |
| Word 3-gram containment | 0.13 | 1.00 | 0.98 | 0.99 | 0.00 | 0.98 | 0.98 | 0.98 | 0.02 |
| MinHash Jaccard (128 perms) | 0.05 | 1.00 | 0.95 | 0.98 | 0.00 | 1.00 | 0.95 | 0.98 | 0.00 |
| Hybrid: MiniLM OR 3-gram containment | 0.68 / 0.13 | 1.00 | 1.00 | 1.00 | 0.00 | 0.96 | 1.00 | 0.98 | 0.06 |
| Hybrid: MiniLM OR TF-IDF | 0.68 / 0.26 | 1.00 | 1.00 | 1.00 | 0.00 | 0.96 | 1.00 | 0.98 | 0.06 |
| Regex and keyword DLP | n/a | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |

## Chunking ablation (MiniLM, documents)

Same model and paste windows, different ways of cutting the documents into indexed passages.

| Index | Doc passages | F1 (in) | R (in) | R at fixed 0.63 | F1 (held-out) | R (held-out) |
|---|---|---|---|---|---|---|
| MiniLM, 120-200 word chunks only (v0.3 before short passages) | 124 | 0.81 | 0.69 | 0.51 | 0.81 | 0.69 |
| MiniLM, pre-fix splitter (duplicated overlap) | 533 | 0.85 | 0.75 | 0.81 | 0.85 | 0.76 |
| MiniLM, long chunks + 60 word passages (current) | 485 | 0.88 | 0.80 | 0.80 | 0.87 | 0.77 |

## Detection per transform (held-out thresholds)

Positives: share detected. Negatives: share falsely flagged.

| Kind | Transform | N | all-MiniLM-L6-v2 | bge-small-en-v1.5 | bge-base-en-v1.5 | jina-embeddings-v2-base-code | nomic-embed-text-v1.5 | TF-IDF cosine (1-2 grams) | Word 3-gram containment | MinHash Jaccard (128 perms) | Hybrid: MiniLM OR 3-gram containment | Hybrid: MiniLM OR TF-IDF | Regex and keyword DLP |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| code | partial | 11 | 1.00 | 1.00 | 1.00 | 0.91 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 |
| code | public_code (negative) | 25 | 0.04 | 0.08 | 0.16 | 0.04 | 0.12 | 0.08 | 0.04 | 0.00 | 0.08 | 0.08 | 0.00 |
| code | reformat | 11 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 |
| code | rename | 11 | 1.00 | 0.82 | 0.82 | 0.73 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 |
| code | rename+reformat | 11 | 1.00 | 0.82 | 0.82 | 0.73 | 0.91 | 1.00 | 1.00 | 0.82 | 1.00 | 1.00 | 0.00 |
| code | verbatim | 11 | 1.00 | 1.00 | 0.91 | 0.91 | 0.91 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 |
| code | wrapped | 11 | 1.00 | 0.91 | 0.91 | 0.36 | 1.00 | 1.00 | 0.91 | 0.91 | 1.00 | 1.00 | 0.00 |
| code | wrapped_public_code (negative) | 25 | 0.04 | 0.08 | 0.12 | 0.04 | 0.08 | 0.00 | 0.00 | 0.00 | 0.04 | 0.04 | 0.00 |
| doc | paraphrase | 36 | 0.78 | 0.28 | 0.72 | 0.19 | 0.61 | 0.89 | 0.39 | 0.28 | 0.89 | 0.94 | 0.03 |
| doc | partial_excerpt | 51 | 0.55 | 0.59 | 0.75 | 0.16 | 0.57 | 1.00 | 0.92 | 0.92 | 0.92 | 1.00 | 0.10 |
| doc | public_text (negative) | 36 | 0.03 | 0.00 | 0.00 | 0.00 | 0.08 | 0.03 | 0.00 | 0.03 | 0.03 | 0.06 | 0.00 |
| doc | reordered_bullets | 29 | 0.97 | 0.86 | 0.93 | 0.86 | 0.86 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.10 |
| doc | summary | 18 | 0.50 | 0.67 | 0.83 | 0.28 | 0.33 | 0.28 | 0.00 | 0.06 | 0.50 | 0.56 | 0.22 |
| doc | tone_rewrite | 18 | 0.44 | 0.61 | 0.61 | 0.17 | 0.33 | 0.61 | 0.22 | 0.22 | 0.50 | 0.72 | 0.00 |
| doc | verbatim | 51 | 0.94 | 0.98 | 0.98 | 0.51 | 0.94 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.14 |
| doc | wrapped_paraphrase | 18 | 0.72 | 0.67 | 0.89 | 0.22 | 0.56 | 0.78 | 0.39 | 0.33 | 0.83 | 0.89 | 0.00 |
| doc | wrapped_prompt | 63 | 0.92 | 0.95 | 0.98 | 0.52 | 0.87 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.19 |
| doc | wrapped_public_text (negative) | 36 | 0.03 | 0.03 | 0.14 | 0.06 | 0.03 | 0.00 | 0.00 | 0.00 | 0.03 | 0.03 | 0.00 |

## Source attribution

For detected document positives (held-out), how often the top hit is the right document.

| Method | Correct source |
|---|---|
| all-MiniLM-L6-v2 | 95% of 220 |
| bge-small-en-v1.5 | 97% of 210 |
| bge-base-en-v1.5 | 93% of 245 |
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
| jina-embeddings-v2-base-code | 768 | 644 MB | 3.2 s | 180.3 s | 75 ms | 433 ms | 1927 MB |
| nomic-embed-text-v1.5 | 768 | 548 MB | 2.3 s | 343.5 s | 87 ms | 590 ms | 3258 MB |
| TF-IDF cosine (1-2 grams) | - | - | 0.0 s | 0.9 s | 1 ms | 2 ms | 138 MB |
| Word 3-gram containment | - | - | 0.0 s | 0.1 s | 1 ms | 2 ms | 67 MB |
| MinHash Jaccard (128 perms) | - | - | 0.0 s | 0.1 s | 0 ms | 1 ms | 67 MB |

Deployed model on the Techvista VM (techvista-vm, 2 vCPU, 0.9 GB RAM): 80 real `/check` calls over HTTP on the VM itself (hybrid matching, PG_THREADS=1, VM shared with the existing Techvista services), p50 208 ms, p95 995 ms, backend RSS 203 MB. The VM is short on memory and pages part of the process out, which is what drives the p95.

Same HTTP test against the backend on this box (8 vCPU): p50 16 ms, p95 58 ms, backend RSS 280 MB.
