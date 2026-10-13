# Optimization log

What changed, why, and what it did to the numbers. Every number here comes from a committed results file
(`eval/results.md` at the named commit) or from the benchmark in `eval/benchmarks.md`, which can be re-run with
`eval/bench_all.sh`.

## What "the model" is

Paste Guard does not train a model. Matching uses `sentence-transformers/all-MiniLM-L6-v2`, a public pretrained
sentence embedding model (384 dimensions, 91 MB ONNX, run on CPU through fastembed), used zero-shot: it embeds
indexed passages and pasted text, and the backend compares them by cosine similarity. Since v0.4 a second,
non-learned signal runs next to it: word 3-gram containment (the share of the pasted window's 3-word sequences
that appear in one indexed passage). The only values fitted to our data are the similarity thresholds that turn
scores into nudge, coach and block, picked by sweeping them on the labelled eval set. No weights were changed and
no eval text was ever used as training data.

## Eval set

472 labelled pastes: 356 against 18 synthetic Calloway Metrics confidential documents (284 positives in nine
transforms, 72 public-text negatives) and 116 against one code repository (66 positives in six transforms, 50
public-code negatives). Positives and negatives were generated with Claude. Main limitation: the negatives are
public text and public code, not same-topic internal text that is not confidential, so false positive rates here
are optimistic for a real company.

## Timeline

| Step | Commit | Change | Doc passages | Doc result at coach level |
|---|---|---|---|---|
| 1 | acf802b | Real embedding model and sqlite-vec index, code only | 0 | n/a (code only) |
| 2 | acf2963 | Documents added: 12 docs, paragraph-aware chunks plus 60 word passages, 280 doc samples | 221 | P 0.98, R 0.82, F1 0.89, FPR 0.03 (threshold 0.62) |
| 3 | cc61c84, ceb4600 | Corpus grown to 18 longer, more varied documents; eval set regenerated (356 doc samples, harder); thresholds retuned | 533 | P 0.99, R 0.75, F1 0.85, FPR 0.04 (0.65) |
| 4 | 06a35b3 | Chunk bug fix: long paragraphs were split with overlap and then packed with overlap again, so the same 30 words appeared up to three times and dragged chunk vectors toward the duplicated text | 485 | P 0.99, R 0.80, F1 0.88, FPR 0.03 (0.63) |
| 5 | v0.4 | Hybrid matching (embedding OR 3-gram containment), separated threshold bands | 485 | P 1.00, R 0.87, F1 0.93, FPR 0.01 (in-sample, deployed bands) |

Step 3 lowered the numbers on purpose: the bigger corpus and harder eval set are more realistic, and the
earlier 0.82 recall was on an easier set.

## Short passages (ablation, re-measured in v0.4)

Re-running MiniLM on the current eval set with only the 120 to 200 word chunks (124 doc passages) against the
current two-granularity index (long chunks plus 60 word passages, 485 passages):

| Index | Recall at the same 0.63 threshold | Best tuned F1 (recall) | Held-out F1 (recall) |
|---|---|---|---|
| Long chunks only | 0.51 | 0.81 (0.69) | 0.81 (0.69) |
| Pre-fix splitter, both granularities | 0.81 | 0.85 (0.75) | 0.85 (0.76) |
| Long chunks + 60 word passages, fixed splitter (current) | 0.80 | 0.88 (0.80) | 0.87 (0.77) |

Short passages are the largest single gain: at a fixed threshold, recall goes from 0.51 to 0.80. A short excerpt
or a one-paragraph summary has no close neighbour among 160 word chunks, because the rest of the chunk dilutes its
vector. (An earlier summary of this as "30% to 80%" is not backed by any recorded run; the measured figure is 51%
to 80% at a fixed threshold, or 69% to 80% when each index gets its own best threshold.) The splitter fix gives a
smaller gain once thresholds are retuned (F1 0.85 to 0.88) and cuts 48 duplicate passages.

## Threshold sweeps

Every sweep scans 0.40 to 0.95 in 0.01 steps and keeps the best F1 with a false positive rate of at most 5%.

| When | Doc best threshold | Doc result | Code best threshold | Code result |
|---|---|---|---|---|
| acf2963 | 0.61 | P 0.97, R 0.83, F1 0.90, FPR 0.04 | 0.51 | P 0.97, R 1.00, F1 0.99, FPR 0.04 |
| ceb4600 | 0.65 | P 0.99, R 0.75, F1 0.85, FPR 0.04 | 0.51 | same |
| 06a35b3 | 0.63 | P 0.99, R 0.80, F1 0.88, FPR 0.03 | 0.51 | same |

v0.3 shipped doc bands of nudge 0.62, coach 0.63, block 0.78. Nudge and coach were one hundredth apart, so the
nudge level almost never fired on its own. v0.4 bands, read off the MiniLM score distribution (doc negatives top
out at 0.67, the five highest are 0.62 to 0.67):

| Level | Doc cosine | In-sample effect |
|---|---|---|
| nudge | 0.58 | recall 0.89, FPR 0.13 (soft "double check", user can continue) |
| coach | 0.64 | best-F1 point, FPR about 0.01 to 0.03 |
| block | 0.74 | above every negative seen; recall 0.51 on its own |

Fingerprint bands: coach at 0.25 containment, block at 0.50. The best tuned containment threshold is 0.14 but the
highest negative scores 0.13, so 0.25 leaves a safety margin. Code bands are unchanged (0.55, 0.65, 0.85).

## Held-out check (new in v0.4)

The thresholds above were picked on the same samples they are scored on. To measure how much that flatters us,
the benchmark splits the 18 documents into two halves of 9 (balanced by sample count; code is split by source
file), tunes on pastes from one half, scores on the other, then swaps. Results for documents:

| Method | In-sample F1 (recall, FPR) | Held-out F1 (recall, FPR) |
|---|---|---|
| MiniLM alone | 0.88 (0.80, 0.03) | 0.87 (0.77, 0.03) |
| Hybrid MiniLM OR 3-gram containment | 0.95 (0.91, 0.03) | 0.94 (0.90, 0.03) |
| Regex and keywords | 0.20 (0.11, 0.00) | 0.20 (0.11, 0.00) |

The gap is small (1 to 3 points), so the tuned threshold is not memorising particular documents. It does not
answer whether a different company's documents would land in the same similarity range; that needs a second corpus.

## Model choice (benchmark, v0.4)

Five pretrained embedding models, three non-neural baselines and two hybrids on the same windows and index. Full
tables in `eval/benchmarks.md`. Held-out document F1, then cost:

| Method | Held-out doc F1 | Held-out code F1 | p50 / p95 per check | Peak RSS |
|---|---|---|---|---|
| all-MiniLM-L6-v2 (deployed) | 0.87 | 0.99 | 9 / 65 ms | 493 MB |
| bge-small-en-v1.5 | 0.85 | 0.93 | 20 / 144 ms | 798 MB |
| bge-base-en-v1.5 | 0.92 | 0.90 | 65 / 474 ms | 1413 MB |
| jina-embeddings-v2-base-code | 0.56 | 0.86 | 75 / 433 ms | 1927 MB |
| nomic-embed-text-v1.5 | 0.82 | 0.95 | 87 / 590 ms | 3258 MB |
| TF-IDF cosine | 0.95 | 0.99 | 1 / 2 ms | 138 MB |
| Word 3-gram containment | 0.86 | 0.98 | 1 / 2 ms | 67 MB |
| Hybrid MiniLM OR 3-gram (deployed) | 0.94 | 0.98 | 16 / 58 ms (HTTP, full backend) | 280 MB (backend process) |
| Hybrid MiniLM OR TF-IDF | 0.96 | 0.98 | not deployed | not deployed |

Peak RSS for single methods is the benchmark scoring process (all chunks plus all eval windows in memory); the
running backend with the deployed hybrid measured 280 MB on this box.

Findings:
- Bigger is not better here. bge-base is the best embedding model for documents (0.92) and the only one that
  reaches 0.83 on summaries, but needs 1.4 GB, which does not fit the 1 GB VM, and is 7 times slower.
- The code-specialised jina model is worst on prose (0.56) and not better on code than MiniLM.
- Lexical methods are very strong on this eval set. TF-IDF alone beats every embedding model. Our paraphrases keep
  names, figures and product terms, and these are exactly what TF-IDF weights. Lexical methods fail on summaries
  (3-gram 0.00, TF-IDF 0.28) and tone rewrites, which is where embeddings earn their place.
- So the two signals cover different transforms: on held-out thresholds, partial excerpts go from 0.55 (MiniLM) to
  0.92 (hybrid) and verbatim from 0.94 to 1.00, while the embedding keeps paraphrase at 0.89 and summary at 0.50.

Decision: keep MiniLM (best accuracy per MB and per millisecond, fits the VM) and adopt the MiniLM OR 3-gram
hybrid. It raised held-out doc F1 from 0.87 to 0.94 at the same 3% FPR and adds no dependency and about 1 MB of
memory (the shingle sets are built from the index at startup). The TF-IDF hybrid scored 2 points higher held-out
but at 0.04 FPR, and needs scikit-learn and a refit on every reindex; it is the first candidate for a next step,
together with harder same-topic negatives to check that lexical gains are not an artefact of easy negatives.

## Latency

| Where | Setup | p50 | p95 |
|---|---|---|---|
| This box, 8 vCPU | `/check` over HTTP, hybrid, 80 eval pastes | 16 ms | 58 ms |
| Techvista VM, 2 vCPU, 1 GB RAM, shared | same test, PG_THREADS=1 | 208 ms | 995 ms |

The VM p95 is driven by memory pressure (130 MB free with Techvista running alongside); the first check after a
restart takes about 10 seconds while the model loads.

## Other v0.4 changes

- Redaction keeps context: headings and code signatures stay, and each removed block becomes
  `[REDACTED: matches <source> paragraphs a-b]` or `lines a-b`. v0.3 replaced each matched window with a bare marker.
- The verdict log always fills the site column: the extension's hostname, else the request's referer, else
  `direct API call`.
