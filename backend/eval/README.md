# Scoring runs against answer keys

Each file in `keys/` is one test question with the companies that must appear (`must_include`) and must not
(`must_exclude`). Score one or more finished runs with:

    python -m app.cli score JOB [JOB ...] --key eval/keys/<question>.json

`s4hana-us.json` has been checked by hand. The Set 1 keys `windchill-us.json`, `netsuite-uk.json`, and
`veeva-india.json` preserve the supplied 39 expected rows and diagnostic notes. The benchmark file did not include
replayable source URLs; one UK row is unidentified and seven Veeva rows are explicitly guesses. Scorecards keep
those labels visible and report the provisional/unresolved counts separately. Other older keys remain drafts.

The reported comparison is Oct 29 pipeline **8/39** versus measured stages 1–4 at commit `52583a5` **11/39 with
zero wrong rows**. The later Stage 5 and name-filter commits are excluded from this branch. A live re-score needs
the original source evidence and configured search provider; importing the answer keys alone does not replay it.

## Candidate recall (did the right companies reach a list?)

Before any page is read, each expected company must be named by some source, with its country known, or no
search for it by name can happen. For one finished run:

    python -m app.cli candidates JOB --key eval/keys/<question>.json

prints, per expected company, the first stage it fell out of the list (not named by any source; named, country
not known; named, placed in another country; named in the asked country) and which sources named it. The same
totals are on `score` as "key: candidate recall". It reads what the run stored, so it makes no search or model
call. A run that had a per-company search pass also shows that pass's own note ("X of Y listed companies
searched").

## Rules for changes

- Measure first. Every change is scored on all the test questions before and after.
- A fix counts only if it raises the must-have score across all keys and adds no must-not rows.
- A fix never names a company, a domain or a list of words. Each "key: lost at" cause is fixed as a general
  mechanism that would work for any question.
- Two or three held-out questions are never tuned against, to catch fixes that only work for the tests.
