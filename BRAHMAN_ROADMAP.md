# Brahman Knowledge Base — Status & Future Goals Roadmap

Last updated: **2026-11-27** (post non-Sonnet batch completion: GLEIF Level 2 RR, two-signal register linking, SEC full crawl, 60-day UK CH Accounts, Form 4 + website leadership, ATS hiring, `kb.company_profile`, and `midmarket_enrich` launch)

---

## 1. Current Verified Baseline

### Raw Legal & Financial Registries (`kb.*`)
| Table | Source | Total Rows | Key Verified Coverage |
| :--- | :--- | ---: | :--- |
| `kb.pdl_company` | People Data Labs Free Dataset | 37,593,138 | 23,568,060 distinct domains |
| `kb.uk_company` | UK Companies House Basic Snapshot | 5,711,779 | 5,179,256 active · 5,711,779 incorporated · 5,479,953 SIC |
| `kb.gleif_company` | GLEIF Golden Copy LEI2 | 3,506,984 | 3,237,262 `ACTIVE` entities |
| `kb.gleif_parent` | GLEIF Level 2 Relationship Records (`RR_2.1`) | 143,331 | Direct parent, ultimate parent & international branch LEIs |
| `kb.sec_company` | SEC EDGAR Bulk Submissions | 994,610 | 2,449 linked domains · 2,089 live homepages · 2,026 ML labels |
| `kb.sec_financial_latest` | SEC EDGAR `companyfacts.zip` (XBRL) | 17,089 | 1,124,623 facts · 13,048 audited annual revenue (`10-K`/`10-Q` tagged) |
| `kb.uk_financials` | UK CH Accounts Bulk iXBRL (60 daily ZIPs) | 878,940 | 871,773 net assets · 747,788 employees · 10,418 turnover |
| `kb.usaspending_recipient` | USAspending Prime Contracts | 94,170 | $826.5B obligated · 1,702 phone-verified domains (+274 candidates) |

### Golden Record (`kb.company_profile`), People, Hiring & Benchmarks
- **Golden Record (`kb.company_profile`):** **88,525** canonical domain profiles (`52,276` live homepages · `4,486` flagged `parked_or_dead` with `checked_at` · `2,310` domains with multiple legal entities attached).
- **Two-Signal Register Links (`kb.domain_register_link`):** `1,966` UK-linked (`902` on-page CH numbers + `1,461` postcode), `3,888` GLEIF-linked (`296` with `ultimate_parent_lei` across `267` parent groups; `2,437` postcode + `1,518` Wikidata `P1278`), `603` India CINs from pages.
- **Decision-Makers (`kb.company_person`):** **10,286** rows across **2,274** unique domains (`7,629` SEC Form 4 officers/directors across `2,204` domains · `1,597` Wikidata across `772` domains · `1,060` website leadership across `109` domains).
- **Structured Hiring (`kb.company_hiring`):** **59** official ATS boards (Greenhouse, Lever, Ashby) with **7,363** open roles by department.
- **Time Series (`kb.company_signal_history`):** Snapshot #1 recorded for all **88,525** profiled domains.
- **Query Latencies (`GIN` + `B-tree` indexes on `kb.company_profile`):**
  - US public audited `>$1B` using Stripe/Cloudflare/Snowflake (`312` hits): **5.56 ms**
  - `SOC 2` or `ISO 27001` actively hiring with company phone (`6` hits): **0.65 ms**
  - UK-linked with verified CH status & net assets `>= £1M` (`56` hits): **0.53 ms**
  - GLEIF subsidiaries rolled up by `ultimate_parent_lei` (`267` groups): **1.04 ms**
- **Active Background Crawl (`tmux: midmarket_enrich`):** Running `50,000` US/GB/IN mid-market (`51–500`) pipeline (`kb-homepages` -> `kb-pages` -> `kb-branches` -> `kb-load-overture` -> `kb-tech` -> `kb-classify` -> `kb-link-registers` -> `kb-load-hiring` -> `kb-build-profile`).

---

## 2. Agreed Architecture & Remaining Work (`#1`–`#6`)

### `#1` — Two-Signal Register Linking & Golden Record (`kb.company_profile`)
- [x] Two-signal register linking (`app/kb/register_link.py`, `kb-link-registers`) — page CH/CIN numbers, `(name_key + postcode)` 1:1 joins, Wikidata LEI.
- [x] Provenance-preserving `kb.company_profile` (`app/kb/profile.py`, `kb-build-profile`) with `sources` JSONB & `legal_entities` array.

### `#2` — Mid-Market (`51–500` Employees) Crawl Expansion
- [x] Added `--midmarket` selector (`app/kb/homepages.py`) and launched `50,000`-domain US/GB/IN pipeline in `tmux` `midmarket_enrich`.
- [ ] Monitor `midmarket_enrich` completion and scale beyond first 50k cohort (`605,958` total US/GB/IN `51–500` PDL domains).

### `#3` — Real Financial Scale & Ownership
- [x] SEC EDGAR `companyfacts.zip` (`kb.sec_financial_latest`, `17,089` filers, `10-K` audited flag).
- [x] UK Companies House Accounts iXBRL (`kb.uk_financials`, 60 daily archives, `878,940` companies).
- [x] USAspending prime contracts + phone-verified linking (`1,702` domains).
- [ ] **External:** India MCA Master Data (`data.gov.in` is `403` WAF-blocked; requires manual CSV download).
- [ ] **External/Optional:** SAM.gov API key (expand UEI -> website links beyond `1,702`), SEC Form D private raises.

### `#4` — Decision-Maker / People Layer (`kb.company_person`)
- [x] PR 1 — Wikidata leadership (`1,597` rows / `772` domains).
- [x] PR 2 — SEC Form 4 officers & directors (`7,629` rows / `2,204` domains).
- [x] PR 3 — Public website `leadership` page extractor (`1,060` rows / `109` domains).
- [ ] **Requires API Key + GDPR Gate:** UK Companies House Officers API (`COMPANIES_HOUSE_API_KEY` + opt-out/legitimate-interest note).
- [ ] **Requires Sonnet:** Normalize `raw_role` titles into canonical seniority/function buckets (sample + classifier).

### `#5` — Hiring Signals, Classification Context & Time Series
- [x] Structured ATS hiring counts by department (`kb.company_hiring`, Greenhouse/Lever/Ashby).
- [x] Signal history Snapshot #1 (`kb.company_signal_history`, `88,525` domains).
- [ ] **Requires Sonnet:** `audience` (`B2B`/`B2C`/`B2G`), `niche`, and `offers` batch labelling + classifier retrain (`kb-train`).
- [ ] **Requires Sonnet:** Non-ATS careers-page department classifier (Sonnet sample -> trained classifier).

### `#6` — Hygiene, Parent/Subsidiary Linking & Query Indexes
- [x] Preserve `real_page = false` (`4,486` flagged `parked_or_dead` with `checked_at`).
- [x] GLEIF Level 2 `parent_lei` / `ultimate_parent_lei` (`143,331` links in `kb.gleif_parent`, rolled up cleanly in `kb.company_profile`).
- [x] `GIN` array indexes + `B-tree` scalar indexes verified at `0.53–5.56 ms` on real queries.
