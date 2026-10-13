# Paste Guard evaluation results

Model: `sentence-transformers/all-MiniLM-L6-v2`. Index: 221 document passages, 109 code chunks. Samples: 396.

Semantic = Paste Guard similarity at or above the kind's **coach** threshold (an actionable warning). Semantic (nudge) also counts the softer nudge level. Regex = secrets rules plus CONFIDENTIAL-style markers plus a sensitive business keyword dictionary.

Thresholds used: doc: nudge 0.6, coach 0.62, block 0.75; code: nudge 0.55, coach 0.65, block 0.85

## Per kind

| Kind | Method | N | Precision | Recall | F1 | FPR |
|---|---|---|---|---|---|---|
| doc | Semantic | 280 | 0.98 | 0.82 | 0.89 | 0.03 |
| doc | Semantic (nudge) | 280 | 0.96 | 0.86 | 0.90 | 0.07 |
| doc | Regex baseline | 280 | 1.00 | 0.11 | 0.19 | 0.00 |
| code | Semantic | 116 | 0.97 | 0.92 | 0.95 | 0.04 |
| code | Semantic (nudge) | 116 | 0.97 | 1.00 | 0.99 | 0.04 |
| code | Regex baseline | 116 | 0.00 | 0.00 | 0.00 | 0.00 |

## Recall per transform (positives) and FPR per negative type

| Kind | Transform | Label | N | Semantic | Regex | Mean similarity |
|---|---|---|---|---|---|---|
| code | partial | positive (detected) | 11 | 1.00 | 0.00 | 0.873 |
| code | public_code | negative (false alarms) | 25 | 0.04 | 0.00 | 0.306 |
| code | reformat | positive (detected) | 11 | 0.91 | 0.00 | 0.835 |
| code | rename | positive (detected) | 11 | 0.91 | 0.00 | 0.841 |
| code | rename+reformat | positive (detected) | 11 | 0.91 | 0.00 | 0.807 |
| code | verbatim | positive (detected) | 11 | 1.00 | 0.00 | 0.878 |
| code | wrapped | positive (detected) | 11 | 0.82 | 0.00 | 0.794 |
| code | wrapped_public_code | negative (false alarms) | 25 | 0.04 | 0.00 | 0.326 |
| doc | paraphrase | positive (detected) | 24 | 0.83 | 0.04 | 0.679 |
| doc | partial_excerpt | positive (detected) | 36 | 0.67 | 0.14 | 0.655 |
| doc | public_text | negative (false alarms) | 40 | 0.05 | 0.00 | 0.464 |
| doc | public_text_combined | negative (false alarms) | 20 | 0.00 | 0.00 | 0.504 |
| doc | reordered_bullets | positive (detected) | 12 | 1.00 | 0.08 | 0.820 |
| doc | summary | positive (detected) | 12 | 0.58 | 0.25 | 0.633 |
| doc | tone_rewrite | positive (detected) | 12 | 0.42 | 0.00 | 0.623 |
| doc | verbatim | positive (detected) | 36 | 0.97 | 0.11 | 0.813 |
| doc | wrapped_paraphrase | positive (detected) | 12 | 0.67 | 0.00 | 0.639 |
| doc | wrapped_prompt | positive (detected) | 36 | 1.00 | 0.14 | 0.797 |
| doc | wrapped_public_text | negative (false alarms) | 40 | 0.03 | 0.00 | 0.473 |

Source attribution: for 208 detected positives, the top match pointed at the right source file 95% of the time.

## Threshold sweep (best F1 with FPR at or under 5%)

- doc: threshold 0.61 gives precision 0.97, recall 0.83, F1 0.90, FPR 0.04
- code: threshold 0.51 gives precision 0.97, recall 1.00, F1 0.99, FPR 0.04

![results](results.png)
