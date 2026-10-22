# Scoring runs against answer keys

Each file in `keys/` is one test question with the companies that must appear (`must_include`) and must not
(`must_exclude`). Score one or more finished runs with:

    python -m app.cli score JOB [JOB ...] --key eval/keys/<question>.json

Only `s4hana-us.json` has been checked by hand; the other keys are drafts to correct.

## Rules for changes

- Measure first. Every change is scored on all the test questions before and after.
- A fix counts only if it raises the must-have score across all keys and adds no must-not rows.
- A fix never names a company, a domain or a list of words. Each "key: lost at" cause is fixed as a general
  mechanism that would work for any question.
- Two or three held-out questions are never tuned against, to catch fixes that only work for the tests.
