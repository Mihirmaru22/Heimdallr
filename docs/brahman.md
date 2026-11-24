# Brahman: the company database

Brahman holds what we know about companies before anyone asks a question. Its aim is to offer what
technographic and company-data vendors sell, at a small fraction of their cost: free and open
sources, our own server, small local models, no paid API.

Rules it follows: company-level facts only (no personal emails, officers or owners); robots.txt
and refusals (403, 429) are always respected, never bypassed; every fact keeps its source and date.

## What each company gets

| Field | Where it comes from |
|---|---|
| Name, website, LinkedIn industry (147 values), size, founded, country, state, city | People Data Labs free company dataset (CC BY 4.0) |
| Sector (20 values) and world region | Our mapping of PDL's industry and country (`backend/app/kb/data/`) |
| Homepage title, description, opening text, generic mailboxes (info@, sales@), postal address | The company's homepage: our own polite fetch, Common Crawl for what it misses |
| Real company page or not (parked, for sale, spam, empty) | Classifier on the homepage |
| Tech company or not | Classifier |
| Micro-sector, for tech companies (36 values: fintech, cybersecurity, IT services...) | Classifier; other companies use PDL's industry as their finer label |
| Products, services, both or none | Classifier |

Each label has a confidence. Below the confidence at which cross-validation reached 80% agreement
with the teacher, the label is stored as "unsure" rather than guessed.

## How it is built

1. **Load PDL** (`kb-load-pdl FILE`): 37.6M companies, 23.6M distinct websites. Domains shared
   by many companies (business.site, instagram.com, linktr.ee...) are platforms, not websites, and
   are skipped.
2. **Read homepages** (`kb-homepages --own-fetch`): each site gets a DNS check (dead domains end
   there), robots.txt, and one GET (https, then www., then http). One try per request, 5 s to
   connect and 10 s to read, 128 different sites at a time. Live sites the fetch misses go to a
   separate Common Crawl lane, which obeys Common Crawl's slow-down requests without holding up
   the fetch. `--biggest-first --country GB,IN,US` reads the largest companies of those countries
   first and skips sites already read.
3. **Teach** (`kb-teach`): a teacher labels a few thousand pages. Claude (Sonnet) labels them in
   the project thread, so there is no API cost: `--export-pages N` writes pages to label,
   `--import FILE` reads the labels back, checked by the same rules as any answer. `--uncertain`
   exports the pages the current classifier is least sure about, which teach it the most. Local
   models through Ollama were tried and were not accurate enough as teachers.
4. **Train** (`kb-train --teacher claude`): four small heads (numpy softmax regression) on a
   multilingual sentence vector of each page (paraphrase-multilingual-MiniLM-L12-v2 via fastembed,
   on the CPU) plus the PDL industry. Each head is cross-validated and its "unsure" threshold set
   before the model is saved to `backend/var/kb/label_model.npz`.
5. **Label** (`kb-classify`): every homepage not yet labelled (`--again` relabels all, which takes
   minutes). `--export-sample 200` writes a random sample for checking by hand.

A first version that compared pages with label descriptions instead of training was about 20%
right on a hand check: it measured topic, not what the company is. Hence the teacher.

On the server, `scripts/kb-label-round.sh` makes each step one command:

    bash scripts/kb-label-round.sh batch 35000          # read + label the 35k biggest unread GB/IN/US companies
    bash scripts/kb-label-round.sh doubt 1000           # export the 1,000 pages the classifier doubts most
    bash scripts/kb-label-round.sh train labels.csv     # import labels, retrain, relabel all, write a sample

## Tables (Postgres schema `kb`)

| Table | Contents |
|---|---|
| `kb.pdl_company` | PDL companies with our sector, ISO country and region |
| `kb.homepage` | One row per website tried: found or not, why not (`dns_dead`, `site_timeout`...), page fields, source crawl or `own`, date |
| `kb.company_label` | Classifier labels and confidences per homepage |
| `kb.teach_label` | Teacher labels, one row per page and teacher |
| `kb.uk_company` | Companies House (loader built, not yet run) |
| `kb.load_log` | Every bulk load with its checks |

A load builds a new table and swaps it in only if its checks pass (for example, at least 90% of the
previous row count); the temporary `*_load` tables are empty otherwise.

## Where it stands (2026-11-24)

- PDL loaded: 37.6M companies.
- Homepages: 10k-site trial done (67% found); first batch of 35k biggest UK/India/US companies
  running, about 4-8 sites a second.
- Classifier, on a hand check of 200 pages: real page vs junk about 97% right; tech company
  precise but missing about 4 in 10; micro-sector right about 9 in 10 when named but unsure for
  half; product/service about 90% right when it answers. Next teaching round targets these gaps.

## Plan

- About 10% of the websites (2.4M) a week, biggest companies and our test countries first. Each
  batch is read, labelled, tested against the benchmark questions and a hand-checked sample, and
  fixed before the next.
- Official registers for addresses and industry codes, one source per PR: Companies House, India
  MCA master data, GLEIF, SEC, Wikidata, then France SIRENE, the Nordic registers, Japan, Australia.
- Technographics (which company uses which product) from the sources the research app already
  has: job ads, vendor case studies, website fingerprints, SEC filings.
- On top of the database: lookalike companies, switch and cross-sell targets, buying signals from
  weekly changes, ranking that learns from users' won and lost leads.
