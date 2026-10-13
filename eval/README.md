# Evaluation: semantic matching vs regex DLP

Question: does Paste Guard catch confidential documents and company code that are pasted in reworded, summarised or excerpted form, which regex rules miss, without raising false alarms on public text?

## Data
`eval/data/doc_pastes.jsonl` and `eval/data/code_pastes.jsonl`. Each line has `id`, `text`, `label` (positive or negative), `source_doc` and `transform`.
- Document positives: verbatim, partial excerpts, paraphrases, summaries, tone rewrites, reordered bullets, and each wrapped in a realistic prompt ("summarise this for me...").
- Document negatives: public prose on similar business topics, alone, combined and wrapped in prompts.
- Code positives: verbatim, renamed, reformatted, renamed and reformatted, partial, wrapped in prompts. Negatives: public code.

## Methods
- Semantic: the real backend logic (`app.semantic`) against the real index; a sample counts as flagged when its best match of the right kind reaches the coach threshold.
- Regex baseline: the secrets rules, CONFIDENTIAL-style markers and a sensitive business keyword dictionary.

## Run
```
./pasteguard reindex
./pasteguard eval --tune
```
Writes `results.md`, `results.png` and per-sample `scores.jsonl`. Thresholds were chosen from this sweep, so treat the numbers as an in-sample estimate; re-run on your own documents before rollout.
