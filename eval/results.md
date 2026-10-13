# Paste Guard evaluation results

Model: `sentence-transformers/all-MiniLM-L6-v2`. Index: 485 document passages, 109 code chunks. Samples: 472.

Paste Guard hybrid = the deployed decision logic: embedding cosine bands OR word 3-gram containment bands, counted at the **coach** level (an actionable warning) unless noted. The model is pretrained and used zero-shot; nothing is trained. Thresholds below were picked from this same set, so these are in-sample numbers; held-out numbers (thresholds tuned on other documents) are in `eval/benchmarks.md`. Regex = secrets rules plus CONFIDENTIAL-style markers plus a sensitive business keyword dictionary.

Embedding bands: doc: nudge 0.58, coach 0.64, block 0.74; code: nudge 0.55, coach 0.65, block 0.85. Fingerprint bands: doc: coach 0.25, block 0.5; code: coach 0.25, block 0.5

## Per kind

| Kind | Method | N | Precision | Recall | F1 | FPR |
|---|---|---|---|---|---|---|
| doc | Paste Guard hybrid (coach) | 356 | 1.00 | 0.87 | 0.93 | 0.01 |
| doc | Paste Guard hybrid (nudge) | 356 | 0.97 | 0.93 | 0.95 | 0.12 |
| doc | Paste Guard hybrid (block) | 356 | 1.00 | 0.73 | 0.85 | 0.00 |
| doc | Embedding only (coach) | 356 | 1.00 | 0.76 | 0.86 | 0.01 |
| doc | Regex baseline | 356 | 1.00 | 0.11 | 0.20 | 0.00 |
| code | Paste Guard hybrid (coach) | 116 | 0.97 | 1.00 | 0.99 | 0.04 |
| code | Paste Guard hybrid (nudge) | 116 | 0.97 | 1.00 | 0.99 | 0.04 |
| code | Paste Guard hybrid (block) | 116 | 1.00 | 0.83 | 0.91 | 0.00 |
| code | Embedding only (coach) | 116 | 0.97 | 0.92 | 0.95 | 0.04 |
| code | Regex baseline | 116 | 0.00 | 0.00 | 0.00 | 0.00 |

## Recall per transform (positives) and FPR per negative type

| Kind | Transform | Label | N | Paste Guard | Regex | Mean embedding similarity |
|---|---|---|---|---|---|---|
| code | partial | positive (detected) | 11 | 1.00 | 0.00 | 0.873 |
| code | public_code | negative (false alarms) | 25 | 0.04 | 0.00 | 0.308 |
| code | reformat | positive (detected) | 11 | 1.00 | 0.00 | 0.835 |
| code | rename | positive (detected) | 11 | 1.00 | 0.00 | 0.841 |
| code | rename+reformat | positive (detected) | 11 | 1.00 | 0.00 | 0.807 |
| code | verbatim | positive (detected) | 11 | 1.00 | 0.00 | 0.878 |
| code | wrapped | positive (detected) | 11 | 1.00 | 0.00 | 0.794 |
| code | wrapped_public_code | negative (false alarms) | 25 | 0.04 | 0.00 | 0.319 |
| doc | paraphrase | positive (detected) | 36 | 0.78 | 0.03 | 0.678 |
| doc | partial_excerpt | positive (detected) | 51 | 0.92 | 0.10 | 0.679 |
| doc | public_text | negative (false alarms) | 36 | 0.00 | 0.00 | 0.475 |
| doc | reordered_bullets | positive (detected) | 29 | 1.00 | 0.10 | 0.835 |
| doc | summary | positive (detected) | 18 | 0.50 | 0.22 | 0.644 |
| doc | tone_rewrite | positive (detected) | 18 | 0.39 | 0.00 | 0.629 |
| doc | verbatim | positive (detected) | 51 | 1.00 | 0.14 | 0.826 |
| doc | wrapped_paraphrase | positive (detected) | 18 | 0.78 | 0.00 | 0.652 |
| doc | wrapped_prompt | positive (detected) | 63 | 1.00 | 0.19 | 0.804 |
| doc | wrapped_public_text | negative (false alarms) | 36 | 0.03 | 0.00 | 0.482 |

Source attribution: for 314 detected positives, the top match pointed at the right source file 98% of the time.

## Threshold sweep (best F1 with FPR at or under 5%)

- doc: threshold 0.63 gives precision 0.99, recall 0.80, F1 0.88, FPR 0.03
- code: threshold 0.51 gives precision 0.97, recall 1.00, F1 0.99, FPR 0.04

![results](results.png)
