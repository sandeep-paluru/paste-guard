# Paste Guard evaluation results

Model: `sentence-transformers/all-MiniLM-L6-v2`. Index: 533 document passages, 109 code chunks. Samples: 472.

Semantic = Paste Guard similarity at or above the kind's **coach** threshold (an actionable warning). Semantic (nudge) also counts the softer nudge level. Regex = secrets rules plus CONFIDENTIAL-style markers plus a sensitive business keyword dictionary.

Thresholds used: doc: nudge 0.62, coach 0.65, block 0.78; code: nudge 0.55, coach 0.65, block 0.85

## Per kind

| Kind | Method | N | Precision | Recall | F1 | FPR |
|---|---|---|---|---|---|---|
| doc | Semantic | 356 | 0.99 | 0.75 | 0.85 | 0.04 |
| doc | Semantic (nudge) | 356 | 0.97 | 0.82 | 0.89 | 0.08 |
| doc | Regex baseline | 356 | 1.00 | 0.11 | 0.20 | 0.00 |
| code | Semantic | 116 | 0.97 | 0.92 | 0.95 | 0.04 |
| code | Semantic (nudge) | 116 | 0.97 | 1.00 | 0.99 | 0.04 |
| code | Regex baseline | 116 | 0.00 | 0.00 | 0.00 | 0.00 |

## Recall per transform (positives) and FPR per negative type

| Kind | Transform | Label | N | Semantic | Regex | Mean similarity |
|---|---|---|---|---|---|---|
| code | partial | positive (detected) | 11 | 1.00 | 0.00 | 0.873 |
| code | public_code | negative (false alarms) | 25 | 0.04 | 0.00 | 0.308 |
| code | reformat | positive (detected) | 11 | 0.91 | 0.00 | 0.835 |
| code | rename | positive (detected) | 11 | 0.91 | 0.00 | 0.841 |
| code | rename+reformat | positive (detected) | 11 | 0.91 | 0.00 | 0.807 |
| code | verbatim | positive (detected) | 11 | 1.00 | 0.00 | 0.878 |
| code | wrapped | positive (detected) | 11 | 0.82 | 0.00 | 0.794 |
| code | wrapped_public_code | negative (false alarms) | 25 | 0.04 | 0.00 | 0.319 |
| doc | paraphrase | positive (detected) | 36 | 0.61 | 0.03 | 0.681 |
| doc | partial_excerpt | positive (detected) | 51 | 0.61 | 0.10 | 0.696 |
| doc | public_text | negative (false alarms) | 36 | 0.03 | 0.00 | 0.478 |
| doc | reordered_bullets | positive (detected) | 29 | 0.93 | 0.10 | 0.836 |
| doc | summary | positive (detected) | 18 | 0.50 | 0.22 | 0.642 |
| doc | tone_rewrite | positive (detected) | 18 | 0.39 | 0.00 | 0.631 |
| doc | verbatim | positive (detected) | 51 | 0.96 | 0.14 | 0.835 |
| doc | wrapped_paraphrase | positive (detected) | 18 | 0.56 | 0.00 | 0.651 |
| doc | wrapped_prompt | positive (detected) | 63 | 0.92 | 0.19 | 0.806 |
| doc | wrapped_public_text | negative (false alarms) | 36 | 0.06 | 0.00 | 0.498 |

Source attribution: for 274 detected positives, the top match pointed at the right source file 96% of the time.

## Threshold sweep (best F1 with FPR at or under 5%)

- doc: threshold 0.65 gives precision 0.99, recall 0.75, F1 0.85, FPR 0.04
- code: threshold 0.51 gives precision 0.97, recall 1.00, F1 0.99, FPR 0.04

![results](results.png)
