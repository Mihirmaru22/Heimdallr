# DIAGNOSIS: "list companies in <place> that use <software X>" (2026-11-24)

Read-only audit of Heimdallr at `origin/main` 78798f5, PR #23 (`claude/project-thread-lc4elm` e9d7d8d) and PR #22 (`claude/project-thread-y8gg04`). No code changed, no live jobs run, no paid model or API called. Ronak asked mid-audit "don't use paid models": none were used; paid options appear below only as priced trade-offs and are marked "needs owner OK".

Tags: **[V]** verified (file:line, command output, commit), **[I]** inferred, **[U]** unknown, with what would resolve it.

## Executive summary

1. **Standing today (main):** US Windchill **2/12** (17%) in 69 min. UK and India have **never been scored on main's pipeline code**: the UK run on that code was stopped 8 minutes in. [V] `eval/runs/scored-ronak-36e4564/runseq.log`
2. **Best stack ever measured (PR #23 code, 52583a5, Nov 2):** **11/39 (28%)**. Per country: US 3/12, UK 5/17 (7/17 if you count "country unconfirmed" rows), India 3/10. Counting only the 32 solid key rows (7 of the 10 Veeva rows are guesses), that is **11/32 (34%)**, or 13/32 with unconfirmed rows. [V] `scored-52583a5/runseq.log`
3. **Precision is fine.** All 10 stored runs: 0 rows the key says must not be there, and 0 wrong-country rows. Two smaller issues: a duplicate (Bharat Serums appears twice), and government bodies listed as "companies". [V]
4. **Bottleneck #1, at 86% of the loss: the company is never discovered.** For 18 of the 21 lost solid rows, no page about that company was fetched in the whole run. [V] (worker-log trace, §3)
5. **For 13 of those 18, the proof is on the software maker's own site** (ptc.com, investor.ptc.com, netsuite.com, oracle.com). Search simply never ranked those pages. PR #23's `vendor_archive` source lists such pages from the maker's sitemap, but it has **never been run live**. [V]/[I]
6. **Bottleneck #2 is time.** Every run hit the 60-minute cap (`partially_completed`). On main, **44% of free-model calls were wasted** (67 rate-limited plus 45 empty, out of 256), which is about 48 minutes of waiting. [V]
7. **Bottleneck #3: country unconfirmed for 2 rows** (UK private firms), plus **1 page that was read but where the reader missed the proof** (Bloom & Wild). [V]
8. **The Brahman KB is not connected to research at all.** Nothing outside `app/kb/` imports it. It also holds no "who uses what" facts, the Companies House loader has never been run, and there is no India register. [V]
9. **The free-only design costs recall in one measurable place.** Per-company proof searches are barred from Tavily, Linkup and Exa (`search/__init__.py:34-36`), and November used only 96/96/90 of the 950/3,800/2,300 monthly allowance. Better models would not fix the main loss: the reader causes only 5% of it. [V]
10. **Smallest unblock:** merge PR #23 → live-test `vendor_archive` → let per-company searches use the paid-credit search APIs within their caps → load Companies House as a country signal. All four cost nothing. The target is US ≥6/12 and UK ≥10/17 with proof on every row (§6c).

---

## §3 Loss table and today's numbers (lead)

### 3.1 Every stored scored run (all set-1 runs on disk)

Source: `~/Downloads/Heimdallr-eval/eval/runs/scored-*/runseq.json` (copied and read) [V]. "Key" means delivered rows out of key rows; "incl. unconf." adds rows where the country was not confirmed.

| Code | Question | Key | incl. unconf. | Delivered | Pages read | Model calls (failed) | Wall time | State |
|---|---|---|---|---|---|---|---|---|
| **36e4564 (= main pipeline)** | Windchill US | **2/12** | 2/12 | 10 | 246 | 257 (67 rate-limited + 45 empty) | 69 min | partial (time cap) |
| 36e4564 | NetSuite UK | **[U] never finished** | | | | | stopped after ~8 min | |
| 52583a5 (PR #23) | Windchill US | 3/12 | 3/12 | 12 | 450 | 139 (15) | 71 min | partial |
| 52583a5 | NetSuite UK | 5/17 | 7/17 | 19 | 451 | 154 (23) | 72 min | partial |
| 52583a5 | Veeva India | 3/10 | 3/10 | 4 (BSV twice) | 556 | 249 (4) | 63 min | partial |
| b7749ae (stage 5) | US / UK / IN | 2/12, 4/17, 0/10 | | | 403/561/334 | 126/154/127 | 62/65/48 min | partial |
| d6b132b / f3fff15 | US / UK / IN | 2/12, 4/17, 2/10 | | | | | 67/38/33 min | partial |
| 7bddb37 to 3c27130 | S/4HANA US (SEC-indexed) | **15/15** | | 15 | | 21-27 | **6-11 min** | partial |

- Main's pipeline code is the same as 36e4564. `git diff 9f94d4e origin/main -- backend/app ':!backend/app/kb'` touches only the fetcher and robots code that kb uses, and y8gg04 differs from 9f94d4e by 6 lines. [V]
- The S/4HANA row shows the pipeline delivers complete, fast answers when a closed list of candidates exists (SEC full-text search). [V] `eval/runs/run_pair.log`

### 3.2 Loss attribution, best stack (52583a5), 32 solid key rows

Method: each run's time window in the eval worker log (`backend/var/logs/worker.log`, 30.6k lines) was matched against every key company's name pattern in every fetched URL, together with the status codes. Proof URLs come from `/mnt/project-files/benchmark-set1-39-rows.md`. Script: `audit-tmp/trace.py`, output in `audit-tmp/trace.json`. [V]

What was checked against the code [V]: the pipeline's own buckets are `delivered / country unconfirmed / elsewhere / filter not met / weak proof / no proof` (`services/companies.py:36,119-128`). The candidate-recall buckets in PR #23 (`services/candidates.py:31-36`) need the job's database rows, which this audit could not reach (§Appendix U1).

| First stage that lost it | US (12) | UK (17) | India solid (3) | Total | % of 21 lost |
|---|---|---|---|---|---|
| **Never discovered** (no page about the company fetched; registry lookups count as discovered) | 9: Boston Sci, NVIDIA*, Komatsu, Welbilt, HP, Cummins, Raytheon, Lockheed, Polaris | 9: Tecni, Vivobarefoot, 2i Testing, GRS, PetShop, Orlebar, Oliver Bonas, Pret, DARING | 0 | **18** | **86%** |
| Discovered, not fetched (robots, budget, dead link) | [U] | [U] | [U] | [U] | the search results list is not logged (U1) |
| Fetched, reader missed the proof | 0 | 1: Bloom & Wild (netsuite.co.uk newsroom page, HTTP 200, not delivered) | 0 | **1** | 5% |
| Proof found, country unconfirmed | 0 | 2: Emerald Technology, Charlotte Tilbury | 0 | **2** | 10% |
| Filtered out (relevance, dedup) | 0 | 0 | 0 | 0 | 0% |
| Dropped in the report | 0 | 0 | 0 | 0 | 0% |
| Delivered | 3 | 5 | 3 | 11 | |

\*NVIDIA: the only page fetched was a cadcamsoftware.vn page about a Windchill-Omniverse integration. That is not proof of use, and the ptc.com blog page that is proof was never fetched. [V]

- **The 7 Veeva "guess" rows** (excluded above): Sun Pharma, Cipla, Dr. Reddy's and Lupin were named as candidates (their homepages were fetched, and sunpharma.com returned 403) but no proof page was ever fetched. Zydus, Glenmark and Biocon were never named. The benchmark file itself says their evidence is weak or not proof, so they may be unprovable from public sources. [V]/[I]
- **Main (36e4564), Windchill:** 10 of 12 lost, **all 10 never discovered**. EnerSys was found on Nov 2 and missed on Nov 5, which is search variance. [V]
- **Where the never-discovered proof actually lives:** 13 of 18 are on a vendor-owned host (US 8: community.ptc.com, ptc.com case studies and blog, investor.ptc.com; UK 5: netsuite.com press releases and oracle.com/uk). The other 5 are on partners or aggregators: lifecycleinsights, appsruntheworld, candjerpconsulting, itsupplychain, homeofdirectcommerce. [V] benchmark file
- **Agrees with the Oct 30 trace** (81 rows, 6 runs: 51% never surfaced in search, 22% reading stopped early, 13% vendor 403, then country and reader). The newer find-rate stop rule removed most of the early stops. Discovery loss stayed. [V] `/mnt/project-files/diagnosis/hypotheses-2026-10-30.md`

### 3.3 Throughput, throttles and failures (from the same log windows) [V]

| Run | Fetches | 403/429 | Blocked hosts (top) | Model calls ok / empty / rate-limited | Mean model latency | Model wait |
|---|---|---|---|---|---|---|
| main q1 | 755 | 13/3 | ptc.com 4 | 144 / 45 / **67** | 11.3 s | 48 min |
| 52583a5 q1 | 1,263 | 32/3 | omron, weatherford, ptc.com | 123 / 7 / 4 | 17.2 s | 37 min |
| 52583a5 q2 | 1,550 | 41/4 | netsuite.com 5, oracle.com 3 | 130 / 10 / 8 | 16.4 s | 38 min |
| 52583a5 q4 | 1,864 | 81/6 | bayer, merckgroup | 244 / 3 / 0 | 8.4 s | 35 min |

- Search calls per job: Keenable (the keyless public endpoint) was called 67-204 times. Tavily, Linkup and Exa were called exactly 11 times each. [V]
- Whole-job failures on the older code: one DNS error killed netsuite-uk-3, one SEC ConnectError killed s4hana-us-3, and a UnicodeEncodeError crashed Veeva d6b132b. The fix (f3fff15) is **not in main**. [V] `git merge-base --is-ancestor f3fff15 origin/main` returned false.

---

## §1 What, why, fit

- **What [V]:** WebData AI is a question → plan → discover → polite fetch → evidence → Excel product (README.md, `backend/app/*`). It is FastAPI, Celery, Postgres with row-level security, Redis, and a React/Vite frontend. Brahman (docs/brahman.md) is a company database in schema `kb`: PDL's 37.6M companies plus homepage labels.
- **Why [V]:** the README states the open question as "which stage loses the answers". The business aim (project memory, 2026-11-20) is to offer what technographic vendors sell at a fraction of their cost. [I: memory, not repo]
- **Intended user [I]:** sales and research users who want lists of target accounts with proof attached.
- **Fit: split across two goals.** [V]
  - The research pipeline is aimed squarely at the geo-technographic query. Questions carry countries, the proof judge returns URL + quote + date (`export/xlsx.py:48`), and country is decided per company (`companies.py:91-109`).
  - Brahman is being built as the candidate universe, but (a) nothing outside `app/kb/` imports it, (b) it holds no "who uses what" facts (docs/brahman.md lists that under Plan), and (c) the homepage classifier answers different questions (tech or not, micro-sector).
  - Since 2026-11-20, all commits have gone to the KB, while the research pipeline's best fixes have sat in PR #23, unmerged for 17 days.

## §2 Status map

| Stage | main | PR #23 | Status / evidence |
|---|---|---|---|
| Plan (question → spec) | works | works | Model plan with a rules fallback that keeps the product (`spec/planner.py:315-330`); the Oct 26 product-drop was fixed in f92bc95, which is in main [V] |
| Discover: SEC, GLEIF, Wikidata, SearXNG, SearchHub | works | works | Listed in the logs; 4 search APIs plus SearXNG (`search/__init__.py`) [V] |
| Discover: per-company targeted search | works (only companies already named) | + leftover-time search (stage 5, b7749ae, **not in PR #23**) | `case_studies.py:242`; barred from capped engines [V] |
| Discover: vendor sitemaps (`vendor_archive`) | **absent** | **built, unit-tested, never run live** | e9d7d8d; my live probe was blocked by sandbox network (U2) [V] |
| Fetch (SSRF-pinned, robots) | works | works + page-failure isolation (f3fff15), title-follow for 403s (e6510bd) | [V] |
| Read / proof (rules + free model) | works, 44% wasted calls | paced gateway (7bddb37), yield-ordered reading (a5c25fc) | [V] |
| Country resolution | works; multi-country = unconfirmed | + second signal for registry matches (52583a5) | `companies.py:91-109` [V] |
| Dedup / rank | works, with a duplicate bug | duplicate-spelling fix only in b7749ae (excluded: it drops "Indian Oil Corporation") | [V] runseq, memory |
| Report / export | works | works | URL, quote, date columns [V] |
| Verified catalog + importers (Companies House, USAspending, Overture) | absent | built, CLI-only, untested live | PR #23 [V] |
| Brahman KB | PDL loaded (37.6M; US 9.38M, UK 3.32M, IN 2.32M); homepages and labels in progress | n/a | `freecompanydatabase-report.txt` [V]; live server counts [U] (U3) |
| KB: Companies House | loader built, **not run** | | docs/brahman.md table [V] |
| KB: India MCA | **not built** | | [V] |
| KB → research link | **none** | none | grep [V] |
| Frontend | PR #22 open (dashboard); PR #26 merged into the #22 branch, not main | | GitHub PR list [V] |
| Tests | **376 passed** | **425 passed, 1 skipped** | local Postgres 16, non-superuser role (§Appendix) [V] |
| Answer keys for set 1 | **absent from main** (only on PR #23) | windchill-us, netsuite-uk, veeva-india .json | `git ls-tree` [V]; eval README says only s4hana-us is hand-checked [V] |
| Run record / replay | text kept to 2,000 chars (`crawl/runner.py:757`); search results not stored | same | [V] |

## §4 Failure register (severity-sorted)

"Loses" means recall loss; "Adds" means wrong rows.

| # | Symptom | Root cause | Stage | Impact | Sev | Class |
|---|---|---|---|---|---|---|
| F1 | 18/21 lost solid rows were never fetched at all | Discovery samples product-keyword search results. There is no enumerable list of candidates for non-SEC questions, and maker pages (sitemaps) are not listed on main | discover | Loses 86% | **P0** | architecture / data-source |
| F2 | Every run is 62-72 min and ends at the cap | `max_job_seconds=3600` (`config.py:59`) plus free-model latency of 8-17 s; on main, 44% of calls rate-limited or empty | read | Caps discovery and reading; goal of ≤30 min not met | **P1** | rate-limits / model |
| F3 | Best fixes not in main | PR #23 open since 2026-11-07; Ronak's local main 03cd213 never pushed; main folder on Mac runs branch y8gg04 | process | Main is 2/12 where PR #23 is 3/12, and the crash-safety fix is missing | **P1** | process |
| F4 | `vendor_archive` never run live | Built after the last scored run | discover | 13/18 never-discovered rows are its target | **P1** | process |
| F5 | Per-company proof searches skip Tavily, Linkup, Exa | Free-only rule (`search/__init__.py:34-36`); caps 950/3,800/2,300 versus 96/96/90 used | discover | Fewer, noisier targeted results [I]; keyless Keenable is shared and variable | **P1** | design (free-only) |
| F6 | UK private firms end as "country unconfirmed" | No UK register loaded (Companies House loader unrun); multi-country addresses settle nothing | country | Loses 2/7 UK found rows (10% of loss) | **P1** | data-source |
| F7 | KB not used by research; no "who uses what" facts | Two separate tracks | product-scope | The candidate universe exists (US 9.4M, UK 3.3M, IN 2.3M) but is unused | **P1** | architecture |
| F8 | One fetch or source error fails the whole job (older code) | Fixed in f3fff15, not in main | infra | Whole runs lost (3 of about 20 stored) | **P1** | code |
| F9 | Reader missed Bloom & Wild on a vendor newsroom page | Free-model or rules reading of the page [U: page text not stored] | read | Loses 5% | P2 | model-quality |
| F10 | "Bharat Serums and Vaccines Limited" and "(BSV)" both delivered | Dedup by spelling | dedup | Adds 1 duplicate | P2 | code |
| F11 | U.S. Army, NASA, Brookhaven delivered as "companies" | Row type not checked | verify | Adds rows of the wrong type [I] | P2 | code |
| F12 | Keys partly guessed (7/10 Veeva); keys only on PR #23 | Keys built from pages found in one diagnosis | eval | The score is a floor; India cannot be judged | P2 | process |
| F13 | Runs not replayable; frontier-reader effect cannot be estimated offline | 2,000-char excerpt; search hits not stored | eval | Loss attribution has [U] gaps | P2 | code |
| F14 | Run-to-run variance (EnerSys found Nov 2, missed Nov 5) | Engines return different results day to day (74%/52% candidate overlap, Oct 30) | discover | ±1-2 rows per question | P2 | data-source |
| F15 | Hardcoded `reputable_hosts` in catalog_store.py (PR #23) | Conflicts with the no-hardcoded-lists rule | catalog | Debt | P3 | code |

**Judging the free-only design [V]/[I].**
- **Where it measurably costs:** (a) on main's code, 44% of model calls were wasted, about 48 minutes of a 69-minute run [V]; (b) per-company searches cannot use the paid-credit search APIs, even though 90%+ of their allowance goes unused [V].
- **Where it does not:** the reader accounts for 5% of the loss, and precision is already clean. A frontier model would mainly buy time, not recall. [I]
- **Untestable:** whether a better model reads proof the free one misses on stored pages. Pages are cut at 2,000 characters (F13). [U]

## §5 Fix matrix

Prices: Claude prices are current list prices [V: claude-api skill table, 2026-11-03]. Search prices come from code comments (`search/__init__.py:143,161`) [V]. Data-vendor prices are from memory and need confirming with the vendor [I].

The per-run token estimate behind the model prices: 250 calls × about 5k input tokens + 300 output tokens [I].

### F1: no list of candidates (P0, 86% of loss)

| Opt | Change | Effort | Δ recall (key) | Δ precision | Cost | Time to effect | Risk / dependency |
|---|---|---|---|---|---|---|---|
| a | Raise `max_job_seconds` and read budget | S | +0-2 rows [I] | 0 | $0 | 1 day | Slower; does not reach pages search never returns |
| b1 | Merge PR #23 and run `vendor_archive` live | S-M | Up to +13/21 (8 US, 5 UK) if sitemaps are reachable [I] | ≈0 | $0 | 2-3 days | ptc.com returns 403 on www pages (4-10 per run) [V]; investor.ptc.com and netsuite.co.uk answer 200 [V] |
| b2 | Title-follow for blocked vendor pages (in PR #23, e6510bd) | S | Recovered 7/8 in the Oct 30 probe [V] | 0 | $0 | with b1 | Copies on other sites need their own proof check |
| c1 | Partner and integrator sitemaps (spkaa, sansasolutions, eurekasolutions, brightbridge...) found from search hosts | M | Targets SRAM, STRATTEC, Folio, Emerald, 2i (some already found) [V] | ≈0 | $0 | 1-2 weeks | Must stay general (no host list) |
| c2 | Aggregators (appsruntheworld, casestudies.com, featuredcustomers) as candidate lists | S-M | Deliveroo and Tecni are on ARTW [V] | ≈0 | $0 to subscription [U] | days | Terms of use must be checked first; secondary proof |
| c3 | Brahman as the universe: country + industry + size filter, then `"<co>" "<product>"` per candidate | L | Large on long-tail mid-market [I] | Risk of name collisions; needs a second identity signal | Free engines: throttled. Linkup $0.005 or Exa $0.004 per search: 2,000 candidates ≈ $8-10 per question | 2-4 weeks | Needs F7; search volume |
| e | Invert the architecture: enumerate first, then verify each company (design proposal 2026-10-30) | L | Structural; S/4HANA is the existence proof (15/15 in 6-11 min) [V] | ≈0 | as c3 | weeks | Large change |
| f | Licensed technographic seeds (HG Insights, Enlyft, ZoomInfo ≈ five-figure $/yr; TheirStack job-ad tech ≈ $50-500/mo; BuiltWith $295-995/mo, front-end only so blind to Windchill/Veeva) as **candidates only**, then public proof | M | High for back-office tools via HG/Enlyft/TheirStack [I] | Same, because proof is still public | See left | 1-2 weeks | Licences forbid resale, which clashes with the vendor-parity strategy; needs owner OK |
| g | Scope: say per question whether the maker publishes customers; offer proof types (job ad, filing, maker story) | S | 0 | Honesty up | $0 | days | Product decision |
| h | Merge PR #23 first; keep one main | S | +1 row now (2→3/12 US) [V] | 0 | $0 | 1 day | Conflict with #22 and #26 frontend |

### F2: time and model throughput (P1)

| Opt | Change | Effort | Effect | Cost | Risk |
|---|---|---|---|---|---|
| a | Merge paced gateway and rules-first reading (PR #23) | S | 429s fell from 67 to 4-8 per run [V] | $0 | none |
| b | Skip model reads on low-yield page kinds (service/product pages 4% yield; `page_yield.json`: offer 7/114) | S | Saves about 10-20% of calls [I] | $0 | small |
| d1 | Paid reader, Claude Haiku 5.5 ($0.10/$0.50 per MTok) | S | No 429s, lower latency [I] | ≈ $0.15-0.20 per run [I] | **Owner said no paid models**; needs owner OK |
| d2 | Claude Sonnet 5.5 ($2/$10) reader and planner | S | Better on hard pages [I] | ≈ $3-3.50 per run [I] | Same |
| d3 | Local model on the Ubuntu server for reading | M | No quota [I] | $0 | qwen2.5/3.5 were too inaccurate as the KB teacher [V memory] |
| e | Read pages in parallel within politeness limits | M | Wall time down [I] | $0 | Free-model rate limits |

### F3, F4, F8: process (P1)

Merge PR #23 into main. Rebase the PR #22 and #26 frontend on top. Retire local main 03cd213. Point start.sh on the Mac at main. Run `vendor_archive` and record the result. **S, $0, 1-2 days.**

### F5: search access (P1)

| Opt | Change | Effort | Cost | Note |
|---|---|---|---|---|
| a | Allow TARGETED on Tavily, Linkup, Exa within the existing monthly caps | S | $0 (allowances already there) | Code change to `kinds` |
| f | Paid search beyond the caps (Linkup std $0.005, Exa lite $0.004 [V code]; Tavily or Serper [I]) | S | $2-16 per question at 500-2,000 per-company searches [I] | Needs owner OK |

### F6: country (P1)

| Opt | Change | Effort | Cost | Effect |
|---|---|---|---|---|
| c1 | Run `kb-load-companies-house` and use `kb.uk_company` as a country signal in research | S-M | $0 | UK private firms (Emerald, Charlotte Tilbury) [I] |
| c2 | PDL `iso2` (90% coverage) as an extra, weaker signal | S | $0 | All countries; PDL is self-reported [I] |
| c3 | India MCA master data loader | M | $0 | Unblocks India private firms [I] |
| g | Show unconfirmed rows separately, never hidden (already the case) | 0 | | [V] `companies.py:9` |

### F7: KB disconnected (P1)

(b) Expose `kb.pdl_company` and `kb.uk_company` to discovery as a candidate source and country signal (M, $0). (e) Store "who uses what" facts found by research runs back into the KB, so each run grows the database (M).

### P2 group

- F9: store full page text (F13), then re-judge misses offline.
- F10: name-normalising dedup, the fix from b7749ae without the regression.
- F11: an organisation-type check against registries or Wikidata.
- F12: hand-check the three set-1 keys and drop the Veeva guesses from the denominator.
- F13: store search hits and full text per job (needed for exact loss tables).
- F14: average two runs per question.

All S-M, $0.

## §6 Verdict and paths

**(a) Can we fulfil the query today?**
- **US: PARTIAL.** 2/12 on main, 3/12 best. Every row has proof, but time is 69-71 min.
- **UK: PARTIAL.** 5/17 best (7 incl. unconfirmed). Not measured on main.
- **India: PARTIAL.** 3/10 best, but 3/3 of the solid rows. Not measured on main.
- **Other geographies: NO evidence.** No scored runs. Country candidates exist in PDL (249 countries) but are unused.
- **Exception: SEC-indexed products in the US: YES** (S/4HANA 15/15, 6-11 min).

**(b) Ranked bottlenecks:**
1. Discovery: candidates never named or fetched (86%).
2. Time and free-model waste (all runs at the cap; 44% wasted calls on main).
3. Country unconfirmed (10%).
4. Reader (5%).

Filters, dedup and the report lose 0.

**(c) Minimum unblock sequence, US + UK, $0:**

| Step | Change | Acceptance test |
|---|---|---|
| 1 | Merge PR #23 into main (frontend rebased) | Tests 425 pass; `eval-run` Windchill US ≥ 3/12 |
| 2 | Live `vendor_archive` probe on Ronak's Mac: `audit-tmp/sitemap_probe.py` (read-only, robots honoured) | Sitemap lists include ≥6 of the 8 PTC-hosted US misses and ≥3 of the 5 NetSuite-hosted UK misses |
| 3 | TARGETED searches allowed on the capped APIs | Allowance usage rises; no cap exceeded; no new must-not rows |
| 4 | Load Companies House and use it as a country signal | Emerald and Charlotte Tilbury move from unconfirmed to delivered; 0 wrong-country rows |
| 5 | Dedup and organisation-type fixes | No duplicate company rows; no government rows for "companies" |
| 6 | Scored runs | **US ≥ 6/12, UK ≥ 10/17**, every row URL + quote + date, 0 must-not rows, ≤ 60 min |

**(d) Plans to reach ≥80% key recall, ≥90% precision, ≤30 min:**

| | Cheapest (respects "no paid models") | Fastest (cost is a column) |
|---|---|---|
| Steps | (c) 1-6, then partner sitemaps (F1 c1), Brahman candidate source + per-company search on free and capped engines (c3), page-yield skipping, India MCA | (c) 1-6 + Haiku or Sonnet 5.5 reader and planner + paid per-company search + licensed technographic seed list (HG, Enlyft or TheirStack) as candidates, public proof kept |
| Cost | $0 setup, $0 per query | ≈ $0.2-3.5 per run for the model + $2-16 per query for search + data licence (≈ $50/mo to five figures a year) [I] |
| Time to effect | 4-6 weeks [I] | 1-2 weeks [I] |
| Expected recall (key) | 60-80% [I]: 18 vendor + ~10 partner/aggregator pages are public for the 32 solid rows [V] | ≥80% [I] |
| Runtime | ~60 min (free-model latency), ≤30 min only with fewer model calls [I] | ≤30 min plausible [I] (S/4HANA 6-11 min [V]) |
| Needs | Nothing new | **Owner approval for every paid item** |

Target adjustment: **80% of the key is realistic. 80% of the true population is not**, because keys were built from public pages (see e1).

**(e) Top 3 structural risks no code removes:**
1. Public proof exists mostly for marquee customers. The true user population (for example, all NetSuite users in the UK) is far larger than any public list, so recall against reality stays low without paid seeds or partnerships. [I]
2. Vendors control access. ptc.com, netsuite.com and oracle.com return 403 to us [V]. Aggregators' terms may forbid use, and robots.txt is never bypassed (Ronak's rule).
3. Licensed technographic data cannot be resold, which undercuts "the same service at a fraction of the cost". On top of that, free search and model capacity is shared and drifts (model ids churn; keyless Keenable), so free-only results vary run to run. [I]/[V]

---

## Appendix

### Commands and raw outputs (abridged)

```
git fetch origin '+refs/heads/*:refs/remotes/origin/*'     # 28 remote branches
git merge-base --is-ancestor {d6b132b,52583a5,b7749ae,36e4564,f3fff15} origin/main   -> all NOT in main; 9f94d4e in main
uv run pytest -q (main, fresh webdata_test, non-superuser role)   -> 376 passed
uv run pytest -q (PR #23 worktree)                                -> 425 passed, 1 skipped
  (with a SUPERUSER role, 4 RLS tests fail by design: test_app_role_is_not_superuser etc.; environment artifact)
python3 audit-tmp/trace.py worker.log runs.json trace.json        -> §3.2/3.3 tables
grep -rn 'app\.kb' backend/app --include=*.py | grep -v '^backend/app/kb/'   -> only cli.py
cat backend/var/search_usage.json (eval stack)   -> {"2026-11": {"tavily": 96, "linkup": 96, "exa": 90}}
python3 audit-tmp/sitemap_probe.py               -> ProxyError for every vendor host (container network blocks them)
```

Scripts and run data: `/mnt/project-files/diagnosis/audit-tmp/` (`trace.py`, `runs.json`, `trace.json`, `sitemap_probe.py`).

### UNKNOWNs and what resolves them

- **U1. Discovered-but-not-fetched split, and PR #23 candidate recall per key company.** Needs the eval database on Ronak's Mac. Run from a PR #23 checkout against the eval stack's database: `python -m app.cli score <job> --key eval/keys/windchill-us.json` for jobs e1681131, 2193fba6, 4b23b3ca (52583a5) and 5b46f4f3 (main). Also run `SELECT status, status_reason, count(*) FROM discovered_urls WHERE job_id='<job>' GROUP BY 1,2;`.
- **U2. Whether vendor sitemaps list the missed companies.** Both this container and the Mac VM lack network access to ptc.com and netsuite.com. On the Mac, run `python3 sitemap_probe.py` (needs `pip install httpx`).
- **U3. Live Brahman counts on the server** (homepages read, labels by country, the 35k batch). On mihir@192.168.1.53, run `psql -c "select count(*), count(*) filter (where found) from kb.homepage; select p.iso2, count(*) from kb.company_label l join kb.homepage h using(domain) join kb.pdl_company p using(domain) group by 1 order by 2 desc limit 10;"` (adjust the join keys to the schema).
- **U4. UK and India on main's code.** One scored run each on main (≤150 pages per the brief), once main includes PR #23.
- **U5. Data-vendor prices and coverage.** Sales quotes; not contacted (no signups).
