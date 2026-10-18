# End-to-end evaluation on the question set

Drafter `openai/gpt-oss-120b`, judge `qwen/qwen3.8-27b`. 5 of 5 questions scored, each through the whole pipeline
(draft, decomposition, verification). A question passes when all the checks of its
category pass (see `src/claimverify/e2e_eval.py`). A smoke test (1 or 2 questions
per category): read the counts, not percentages.

**Questions passed: 4/5.**

## By category

| Category | Passed | Checks |
|---|---|---|
| single_source | 1/1 | sources used, no false conflict, no contradiction |
| multi_source | 1/1 | sources used, no false conflict, no contradiction |
| conflict | 0/1 | sources used, conflict found |
| out_of_corpus | 1/1 | no false conflict, nothing supported |
| false_premise | 1/1 | sources used, no false conflict, premise caught |

## By check

| Check | Passed |
|---|---|
| sources used | 4/4 |
| no false conflict | 4/4 |
| no contradiction | 2/2 |
| conflict found | 0/1 |
| premise caught | 1/1 |
| nothing supported | 1/1 |

## Recorded, not graded

- Claims: 36 (7.2 per question), of which 3 about the answer itself (meta, not verified), near-identical pairs: 3
- Verdicts: 31 supported, 0 contradicted, 0 contested, 2 unverifiable, 0 error
- Tokens: 162262 (32452 per question), rate-limit waits: 831 s, time: 1062 s

## Every question

Proofs: the question's quotes found in the drafter's passages / in the judge's passages.

Claims: verified + meta (about the answer itself, not verified).

| Id | Category | Result | Failed checks | Proofs (draft / judge) | Claims | Verdicts |
|---|---|---|---|---|---|---|
| q01 | single_source | ✓ pass | – | 0/1 / 0/1 | 7 + 0 | 6 supported, 1 unverifiable |
| q04 | multi_source | ✓ pass | – | 0/2 / 1/2 | 12 + 0 | 12 supported |
| q05 | conflict | ✗ fail | conflict found | 1/2 / 2/2 | 9 + 0 | 1 unverifiable, 8 supported |
| q07 | false_premise | ✓ pass | – | 1/1 / 1/1 | 5 + 0 | 5 supported |
| q09 | out_of_corpus | ✓ pass | – | – | 0 + 3 | – |
