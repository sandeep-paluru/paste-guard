# Eval: semantic vs regex

Question: does semantic matching catch disguised copies of private code that regex rules miss, without too many false positives?

## Datasets (public only)
- POJ-104: about 52k programs in 104 problem classes. Used as stand-in "private code" to index.
- BigCode PII-in-code: about 12k labeled snippets. Scores the secrets and PII layer.
- ai4privacy: about 300k texts with PII labels. Scores PII in prose pastes.
- Novel set: about 500 Claude-generated disguised copies of a public repo (renamed identifiers, reordered functions, comments stripped, ported style), mixed with negatives (unrelated code, common boilerplate).

## Method
1. Index the source repo with the backend.
2. Run every sample through /check in regex-only mode and in semantic mode.
3. Report precision, recall, and F1 per mode, plus a threshold sweep.

## TODO
- harness.py (Day 3)
- dataset download scripts
