# Heimdallr

Research that turns live web evidence into cited, verifiable answers.

`main` was emptied on 2026-10-19 to start again. Everything built before that date is kept, in
full, on the branch `archive/v4-2026-10-19` (last commit `f86120c`):

    git fetch origin archive/v4-2026-10-19
    git show archive/v4-2026-10-19:<path>          # read one file
    git checkout archive/v4-2026-10-19 -- <path>   # bring one file back

Worth knowing about what is in there, before rebuilding any of it:

- `src/argus/investigation/live_web/run_recorder.py` records every search and page fetch of a run,
  so a run can be replayed offline instead of re-run against the live web.
- `src/argus/evals/run_scorecard.py` writes one row of numbers per run (answers, evidence strength,
  gate refusals, pages, time), which is how a change is judged by something other than one report.
- `src/argus/evals/list_benchmark.py` scores a run against a reference list.
- `src/argus/intake/brief.py` is the research brief: the form's fields handed over as fields.

The open question the rebuild exists to answer: of the stages between a question and an answer
(search, fetch, read, verify, report), which one loses the answers.
