# Public catalog sources

The catalog combines the existing Wikidata, GLEIF, SEC, news, and case-study discovery work with three public-data enrichments. Source adapters write claims into the same tenant-scoped catalog; each claim keeps normalized and original values, source URL, source record ID, source group, license note, retrieval time, and review status.

## Sources

| Source | Useful for | Evidence handling |
| --- | --- | --- |
| Companies House | UK company number, legal name, status, incorporation date, SIC codes, registered office | Exact normalized company-name match only. Official register facts are verified as legal-entity facts. Registered office is not labeled headquarters. API key is optional and read from `WEBDATA_COMPANIES_HOUSE_API_KEY`. |
| USAspending.gov | US federal award recipient and award details | Exact recipient-name matches are stored as verified award facts with `received_award` relationship. An award is procurement evidence; it never establishes software use or headquarters. |
| Overture Places | Possible business location, address, phone, website, coordinates | Import requires a regional bounding box and exact existing catalog-name match. Every result stays in review; Overture's confidence score measures place existence, not attribute accuracy. Duplicate places and incomplete attributes are known quality issues. |

The Companies House API requires API credentials and documents a 600-request-per-five-minute limit; the shared public-data client honors `Retry-After`, bounds retries, and stops on 403. See the [API overview](https://developer.company-information.service.gov.uk/overview) and [developer guidelines](https://developer.company-information.service.gov.uk/developer-guidelines).

USAspending documents its award search endpoint as public and unauthenticated. See the [endpoint reference](https://api.usaspending.gov/docs/endpoints) and [API tutorial](https://api.usaspending.gov/docs/intro-tutorial).

Overture Places can be downloaded by bounded area using the official Python CLI. Licensing varies by contributing source (including CDLA Permissive 2.0 and Apache 2.0); keep the record's source attribution and consult [Overture Places](https://docs.overturemaps.org/guides/places/) and [attribution/licensing](https://docs.overturemaps.org/attribution/). Its confidence score is an existence score, and the theme documentation reports duplicates and low attribute completeness.

## Import

Run these from `backend/` after applying migrations to the intended database. Use the organization UUID from the application.

```sh
# UK legal-entity facts (requires WEBDATA_COMPANIES_HOUSE_API_KEY)
python -m app.cli catalog-companies-house ORG_UUID "Company Limited"

# US federal award-recipient facts; one bounded result page, max 100
python -m app.cli catalog-usaspending ORG_UUID "Example Corporation" --limit 20

# Download only a region you need, then import the local file as review-only claims.
overturemaps download --bbox=-71.2,42.2,-70.9,42.5 --type=place -f geojson -o var/overture/boston.geojson
python -m app.cli catalog-overture ORG_UUID var/overture/boston.geojson --bbox -71.2 42.2 -70.9 42.5 --release latest
```

The Overture file is local, ignored by Git, and should be bounded before import. Per-source license attribution is retained on each imported claim. Do not download the global dataset for a company lookup.

## Verification and search

Explicit confirmed first-party or official evidence may verify the specific claim it supports. Two different source groups may corroborate a matching fact when the excerpts are distinct and no source in the same field contradicts it; identical copied excerpts count as one signal. Claims without that evidence stay in review. A person can verify, reject, or reopen a claim in the database page.

Search the catalog by company/website/fact text, region, software, or field and value. Review-state claims are excluded unless “Include claims awaiting review” is selected.
