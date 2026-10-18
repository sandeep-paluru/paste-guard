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
public-code negatives). Positives and negatives are synthetic. Main limitation: the negatives are
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

## v0.5: an "accurate" profile for a desktop PC (2026-10-13)

Question: with RAM no longer a limit (backend on a desktop instead of the 1 GB VM), what is the most accurate setup?
Second constraint added during the work: it has to stay real-time, full `/check` p95 under 100 ms on a normal CPU,
and false alarms at most 3%.

What changed in the method: the false alarm budget used when tuning every threshold went from 5% to 3%, and all
earlier numbers were recomputed with it. Still no training or fine-tuning anywhere. Every embedding model is a public
pretrained checkpoint used zero-shot; only thresholds (and TF-IDF's vocabulary and IDF weights from the indexed
corpus) are fitted. Held-out = 2-fold split by source document.

Tried: bge-base, bge-large, mxbai-embed-large, gte-large, each alone and OR-combined with 3-gram and TF-IDF, plus
MiniLM OR TF-IDF and MiniLM OR 3-gram OR TF-IDF. arctic-embed-l and paraphrase-mpnet were queued but dropped once
the latency rule came in, since they are the same size class as the large models that already failed it.

What we learned:
- The large models do not win. bge-large, mxbai-large and gte-large alone reach held-out doc F1 0.88 to 0.89, barely
  above MiniLM (0.87), at 190 to 210 ms p50 and over 1 s p95 per check, and about 4 GB RAM. They help summaries
  (0.72 to 0.83 vs 0.50) but that is not worth 20x the latency.
- bge-base looks best on raw recall (0.96 in hybrids) but its false alarm rate on held-out negatives is 7% to 8%,
  mostly on public text wrapped in a prompt (14% flagged). It fails the 3% rule before speed even matters, so ONNX
  quantization to make it faster would not rescue it.
- TF-IDF alone is a surprisingly strong baseline on documents (F1 0.95, 1.4% false alarms) because most real leaks
  keep the document's distinctive vocabulary: product names, numbers, people. It is weak on summaries (0.28).
- The three signals are complementary. MiniLM covers meaning (paraphrase, summary), 3-gram covers exact excerpts,
  TF-IDF covers reworded text that keeps the rare words (tone rewrites 0.50 to 0.72).

Decision: profile `accurate` = MiniLM OR 3-gram OR TF-IDF. Held-out documents: F1 0.966, recall 0.94, precision
0.99, false alarms 2.8% (2 of 72 negatives), vs 0.943 / 0.90 / 0.99 / 2.8% for the default. Summaries 0.56,
tone rewrites 0.72. Full `/check` over HTTP on the box: p50 19 ms, p95 56 ms, 379 MB RSS. Same model and index as
the default, so no reindex. TF-IDF is turned off for code in this profile: on code it added false alarms (6% held-out
on 50 negatives) without adding recall, which was already 1.00.

Honest limits: 72 document negatives means one false alarm moves the rate by 1.4 points, so 2.8% vs 4.2% is a
one-sample difference. Summaries remain the weak spot at 56%. The default profile on the VM is unchanged.

## 0.5.1: accurate becomes the default

- The default profile is now `accurate` (MiniLM OR 3-gram OR TF-IDF). The old setup is `profile = "fast"`. The numbers
  above are unchanged: held-out document F1 0.966 against 0.943, same false alarm rate of 2.8%. After deploy on the 1 GB
  Techvista VM, a short document paste check takes about 0.10 s end to end and the service uses about 370 MB.
- Huge inputs: with more than 48 windows, half of the embedded windows are chosen by TF-IDF score and half are sampled
  evenly. Before this, a confidential section near the end of a very long paste or file could fall outside the windows
  that were embedded. Pastes over 2 MB characters are rejected with HTTP 422. No new accuracy numbers were measured for
  this change; it is covered by edge-case tests.
- Unicode cleanup before matching: zero-width characters stripped, NFKC, common Cyrillic and Greek look-alikes mapped
  to Latin. This closes an easy evasion (inserting invisible characters or swapping letters). It was added as a
  correctness fix and is covered by tests, not by the benchmark set.
- The model is still pretrained all-MiniLM-L6-v2 used as is. Nothing was trained; only thresholds were tuned.

## 0.6.0: two-step fast path (2026-10-14)

Question: most of the time per check goes to the MiniLM embedding, but many pastes share almost no vocabulary with any indexed document. Can a cheap first step decide those without the model? The idea comes from Google DeepMind's on-device Gemma scam detector (October 2026), which runs a cheap classifier first and the heavier model only when needed.

What changed (`semantic()` in `backend/app.py`, config `[fast_path] enabled = true, skip_below = 0.10`, `PG_FAST_PATH=0` turns it off):
- Step 1 runs 3-gram containment and TF-IDF on every window, a few ms.
- MiniLM is skipped when a cheap check already reaches block. The embedding cannot raise the verdict past block, so the outcome is identical.
- MiniLM is also skipped when the best TF-IDF score against any indexed passage is below 0.10, meaning almost no shared vocabulary.
- 0.10 was picked because on the eval no positive whose MiniLM score is at or above 0.60 has a TF-IDF score below 0.12, in either held-out fold. So 0.10 leaves a small margin below the lowest such positive.

Measured with `eval/fastpath_eval.py`, which runs `app.decide()` on all 472 eval pastes with the fast path off and on (`eval/bench/fastpath.json`, chart `eval/bench_fastpath.png`). Flagged = coach or block verdict, deployed thresholds.

| Set | Recall off / on | False alarm rate off / on | p50 off / on | p95 off / on |
|---|---|---|---|---|
| All 472 pastes | 0.946 / 0.946 | 2.5% / 2.5% | 11.0 / 3.6 ms | 70.1 / 21.9 ms |
| Documents | 0.933 / 0.933 | 1.4% / 1.4% | 9.8 / 3.3 ms | 44.0 / 16.2 ms |
| Code | 1.00 / 1.00 | 4% / 4% (2 of 50) | 17.6 / 5.2 ms | 132.3 / 46.7 ms |

MiniLM was skipped on 58.5% of the eval pastes. Exactly one verdict changed out of 472: a negative went from nudge to allow, and nudge is not a flag. Per held-out fold, recall and false alarm rate are identical with the fast path off and on (document fold A recall 0.939, FPR 0.0; fold B recall 0.927, FPR 2.7%). The 4% code false alarm rate is the same as in 0.5.1 and remains a known limit. Timings are in-process backend logic on the 8 core box.

Caveat: the eval set is mostly near-matches of confidential text. In daily use most pastes are unrelated text, so the skip rate should be higher. I did not measure that.

HTTP latency of real `/check` calls (`eval/http_latency.py`):

| Machine | 0.5.1 p50 / p95 | 0.6.0 p50 / p95 | File |
|---|---|---|---|
| This box (8 CPU, 15.6 GB) | 19.1 / 56.1 ms | 7.3 / 22.5 ms | `eval/bench/box_latency_0.6.json` |
| Techvista VM (2 CPU, 0.9 GB, shared, PG_THREADS=1) | 130.6 / 801.9 ms | 84.0 / 397.2 ms | `eval/bench/vm_latency_0.6.json` |

The VM tail is memory pressure and swap, not the model. On a normal laptop it meets the p95 under 100 ms rule.

Cold start: the backend now loads the model and runs one warm-up check at startup (`PG_NO_WARMUP=1` skips it). The first `/check` after a restart went from 1.29 s to 0.024 s on the box, where startup itself grew from 0.45 s to 1.75 s. On the VM it went from about 8.5 s to 0.18 s, and the warm-up takes 18 s at startup there. `/health` now reports the fast path settings and counters and `warmup_ms`.

Tried and rejected: int8 dynamic quantization of MiniLM (onnxruntime `quantize_dynamic`). The model shrank from 90.4 MB to 22.9 MB and a text took 3.9 ms instead of 6.6 ms, but the embeddings drifted. Cosine to the fp32 vectors averaged 0.952 and went as low as 0.888 on 120 doc pastes. That shift is larger than the gap between our coach and block bands, so every threshold would need re-tuning to save about 3 ms per text, which the fast path already beats. I kept fp32. Batching: the windows of a paste were already embedded in one batch (batch_size 16), so nothing changed there.

Secrets scanner (not a latency change): new rules for Anthropic, OpenAI project, service account and admin keys, GitHub fine-grained tokens, AWS temporary keys, Google, Stripe, Slack webhooks, JWTs, Hugging Face, GitLab, npm, SendGrid, Twilio, Azure, xAI and database URLs with a password. Overlapping matches keep the longest span. The tests are in `tests/test_secrets_formats.py`; the total is now 84 pytest tests.

The model is still pretrained all-MiniLM-L6-v2 used zero-shot. Nothing was trained; only thresholds were tuned.
