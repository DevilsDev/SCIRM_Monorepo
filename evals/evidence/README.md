# Evidence Engine evaluation (public data)

How well SCIRM answers questions about a supplier from public records, and whether
it ever states something its sources don't support.

```
python evals/evidence/run_eval.py                       # in-memory store (development)
TEST_POSTGRES_URL=... python evals/evidence/run_eval.py --postgres   # what ships
python evals/evidence/fetch_corpus.py                   # refresh the corpus
```

This is a **synthetic** set built from FDA and GDACS records. It is not the
partner-labelled gold set the roadmap calls for; that still needs design partners.

## What is measured

- **Corpus:** 7,670 real records (`data/corpus.jsonl.gz`): FDA recalls and warning
  letters from the past two years, FDA's current shortage and import-alert lists,
  and GDACS alerts.
- **Questions:** written by a separate agent that never saw the retrieval code. It
  phrased them as a buyer would ("sterility problems", "held at the US border") and
  labelled relevance with rules over the raw FDA fields (`relevant.any_regex`),
  independent of how retrieval works. Each set includes "nothing matches" questions
  (a topic the supplier has no records for, or an invented supplier).
  - **Set A** (`questions.json`, 45 questions): used while developing retrieval, so
    its numbers are optimistic.
  - **Set B** (`questions_b.json`, 44 questions, 18 different suppliers, short,
    rambling and misspelt questions): written afterwards and **never tuned on. It
    is the honest number.** One retrieval fix was made after set B existed: topic
    words no longer match company names. A unit test found that bug, not set B,
    and set B was re-run after it.
- **Citation checker:** 400 correct sentences composed from records, then the same
  sentences corrupted on purpose: wrong date, firm, recall class, number or record
  type, a wrong or unknown citation, or no citation at all.

## Results (2026-10-20, PostgreSQL, keyword retrieval v1)

| | Set A (tuned on) | **Set B (held out)** |
|---|---|---|
| recall@10 | 0.91 | **0.83** |
| MRR | 0.94 | **0.94** |
| Questions with relevant records but no hit | 0 of 36 | 2 of 34 |
| "Nothing matches" answered without citing records | 9 of 9 | 9 of 10 |

**Citation checker** (600 sentences × 3 seeds = 1,800 correct sentences from real records):
**0 wrongly rejected**. Corrupted copies caught, by error type:

| Error | Caught |
|---|---|
| no citation / unknown citation / citation to an unrelated record | 100% |
| wrong date, firm, recall class, record type | 99.7–100% |
| wrong number | 97–100% (few sentences contain numbers) |
| negation ("FDA never published…") | 100% |
| invented severity ("a minor recall") | 100% |
| invented count ("three recalls") | 99–100% |
| facts of two records mixed in one sentence | 99.3–99.8% |
| overgeneralisation ("all products") | 98.5–99.5% (misses: records that themselves say "all") |

An earlier version reported about 100% while measuring only the first two rows.
Negations, quantifiers, number words and judgements were then free vocabulary, and
claims were checked against the union of their citations, so "FDA found no problems
at X [S1]" passed. Both have since been fixed, and the new error types are in the CI
gate.

**What the checker still cannot catch:** a conclusion that recombines words from
one record into a false statement, for example reordering who did what to whom
using only words from that record. That needs an LLM reviewer, planned for when a
model is configured.

## Known weaknesses (from set B, not fixed, so B stays honest)

- **Vocabulary gaps:** "a different tablet found in the bottle" is read as a
  packaging question, but FDA writes "foreign tablets".
- **Mixed questions lose a topic:** "sterility … or heavy metal like arsenic" keeps
  only the more specific topic. Topics are combined by preferring specific over
  general, not by OR.
- **Topic words match product names:** a recall of "sterile alcohol prep pads" for
  weak alcohol is returned for a sterility question.
- **The checker verifies specifics, not reasoning.** Dates, classes, numbers, record
  types, names and vocabulary must come from the cited record. Its closed
  vocabulary rejects free paraphrase, so a model's answer often falls back to the
  records' own wording.

**Next:** vector search, once an embedding provider is chosen, should help the
paraphrase gaps. Matching topics against the recall *reason* field rather than the
whole record would fix the product-name hits. Both are to be measured on a new
held-out set C.

`tests/evidence/test_evidence_gate.py` runs this in CI on PostgreSQL and fails on
regressions.
