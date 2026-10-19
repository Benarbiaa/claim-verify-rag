# End-to-end evaluation on the question set

Drafter `openai/gpt-oss-120b`, judge `qwen/qwen3.8-27b`. 10 of 10 questions scored, each through the whole pipeline
(draft, decomposition, verification). A question passes when all the checks of its
category pass (see `src/claimverify/e2e_eval.py`). A smoke test (1 or 2 questions
per category): read the counts, not percentages.

**Questions passed: 9/10.**

## By category

| Category | Passed | Checks |
|---|---|---|
| single_source | 2/2 | sources used, no false conflict, no contradiction |
| multi_source | 2/3 | sources used, no false conflict, no contradiction |
| conflict | 1/1 | sources used, conflict found |
| out_of_corpus | 2/2 | no false conflict, nothing supported |
| false_premise | 2/2 | sources used, no false conflict, premise caught |

## By check

| Check | Passed |
|---|---|
| sources used | 8/8 |
| no false conflict | 9/9 |
| no contradiction | 4/5 |
| conflict found | 1/1 |
| premise caught | 2/2 |
| nothing supported | 2/2 |

## Recorded, not graded

- Claims: 79 (7.9 per question), of which 7 about the answer itself (meta, not verified), near-identical pairs: 6
- Verdicts: 68 supported, 1 contradicted, 1 contested, 2 unverifiable, 0 error
- Tokens: 355716 (35571 per question), rate-limit waits: 1934 s, time: 2379 s

## Every question

Proofs: the question's quotes found in the drafter's passages / in the judge's passages.

Claims: verified + meta (about the answer itself, not verified).

| Id | Category | Result | Failed checks | Proofs (draft / judge) | Claims | Verdicts |
|---|---|---|---|---|---|---|
| q01 | single_source | ✓ pass | – | 0/1 / 0/1 | 7 + 0 | 6 supported, 1 unverifiable |
| q02 | single_source | ✓ pass | – | 0/1 / 1/1 | 5 + 0 | 5 supported |
| q03 | multi_source | ✓ pass | – | 0/2 / 2/2 | 7 + 0 | 7 supported |
| q04 | multi_source | ✓ pass | – | 0/2 / 1/2 | 12 + 0 | 12 supported |
| q05 | conflict | ✓ pass | – | 1/2 / 1/2 | 11 + 1 | 10 supported, 1 contested |
| q06 | multi_source | ✗ fail | no contradiction | 2/2 / 2/2 | 22 + 0 | 20 supported, 1 unverifiable, 1 contradicted |
| q07 | false_premise | ✓ pass | – | 1/1 / 1/1 | 5 + 0 | 5 supported |
| q08 | false_premise | ✓ pass | – | 1/1 / 1/1 | 3 + 2 | 3 supported |
| q09 | out_of_corpus | ✓ pass | – | – | 0 + 3 | – |
| q10 | out_of_corpus | ✓ pass | – | – | 0 + 1 | – |
