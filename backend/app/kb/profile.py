"""Provenance-preserving Golden Record (kb.company_profile) and snapshot time series (kb.company_signal_history)."""

from __future__ import annotations

import time
from datetime import date

PROFILE_COLS = (
    "domain", "company_name", "country", "iso2", "city", "state", "size_band", "founded",
    "homepage_found", "homepage_url", "homepage_status", "checked_at",
    "real_page", "tech_company", "micro_sector", "offering",
    "sp500_symbol", "sec_cik", "sec_ticker", "sic", "sic_description",
    "uk_company_number", "uk_status", "uk_incorporated",
    "gleif_lei", "gleif_status", "parent_lei", "ultimate_parent_lei", "parent_name", "ultimate_parent_name",
    "india_cin", "legal_entities",
    "annual_revenue", "revenue_form", "revenue_end", "sec_audited",
    "uk_net_assets", "uk_turnover", "uk_employees",
    "usaspending_obligated", "usaspending_awards",
    "company_phone_count", "branch_phone_count", "clean_email_count", "branch_count",
    "open_jobs", "ats", "leadership_count",
    "techs", "compliance", "countries", "hiring_departments", "sources",
)


def _create_profile_table(conn, name: str) -> None:
    conn.execute(f"""
        CREATE TABLE kb.{name} (
            domain text PRIMARY KEY,
            company_name text,
            country text,
            iso2 text,
            city text,
            state text,
            size_band text,
            founded integer,
            homepage_found boolean NOT NULL DEFAULT false,
            homepage_url text,
            homepage_status text NOT NULL,
            checked_at timestamptz,
            real_page boolean,
            tech_company boolean,
            micro_sector text,
            offering text,
            sp500_symbol text,
            sec_cik integer,
            sec_ticker text,
            sic text,
            sic_description text,
            uk_company_number text,
            uk_status text,
            uk_incorporated date,
            gleif_lei text,
            gleif_status text,
            parent_lei text,
            ultimate_parent_lei text,
            parent_name text,
            ultimate_parent_name text,
            india_cin text,
            legal_entities jsonb NOT NULL DEFAULT '[]'::jsonb,
            annual_revenue double precision,
            revenue_form text,
            revenue_end date,
            sec_audited boolean,
            uk_net_assets double precision,
            uk_turnover double precision,
            uk_employees integer,
            usaspending_obligated double precision,
            usaspending_awards integer,
            company_phone_count integer NOT NULL DEFAULT 0,
            branch_phone_count integer NOT NULL DEFAULT 0,
            clean_email_count integer NOT NULL DEFAULT 0,
            branch_count integer NOT NULL DEFAULT 0,
            open_jobs integer NOT NULL DEFAULT 0,
            ats text,
            leadership_count integer NOT NULL DEFAULT 0,
            techs text[] NOT NULL DEFAULT '{{}}',
            compliance text[] NOT NULL DEFAULT '{{}}',
            countries text[] NOT NULL DEFAULT '{{}}',
            hiring_departments text[] NOT NULL DEFAULT '{{}}',
            sources jsonb NOT NULL DEFAULT '{{}}'::jsonb,
            updated_at timestamptz NOT NULL DEFAULT now()
        )""")


def _ensure_prereq_tables(conn) -> None:
    from app.kb import gleif, hiring, people, register_link

    conn.execute(register_link.SCHEMA_SQL)
    conn.execute(gleif.PARENT_SCHEMA_SQL)
    conn.execute(hiring.SCHEMA_SQL)
    conn.execute(people.SCHEMA_SQL)


def refresh_company_profile(conn) -> dict[str, int]:
    """Rebuild kb.company_profile with field-level provenance, GLEIF hierarchy, and GIN + B-tree indexes."""
    t0 = time.monotonic()
    _ensure_prereq_tables(conn)
    conn.execute("DROP TABLE IF EXISTS kb.company_profile_load")
    _create_profile_table(conn, "company_profile_load")

    sql = """
        WITH universe AS (
            SELECT domain FROM kb.homepage
            UNION SELECT DISTINCT domain FROM kb.sp500_member WHERE domain IS NOT NULL
            UNION SELECT DISTINCT domain FROM kb.sec_company WHERE domain IS NOT NULL
            UNION SELECT DISTINCT domain FROM kb.domain_register_link
        ),
        pdl AS (
            SELECT DISTINCT ON (domain) domain, name, country, iso2, city, state, size, founded
            FROM kb.pdl_company
            WHERE domain IN (SELECT domain FROM universe) AND domain_rows <= 20
            ORDER BY domain, (iso2 = 'US') DESC, founded NULLS LAST
        ),
        sec AS (
            SELECT DISTINCT ON (domain) domain, cik, ticker, name, sic, sic_description, city, state
            FROM kb.sec_company
            WHERE domain IS NOT NULL
            ORDER BY domain, rank NULLS LAST, cik
        ),
        sp AS (
            SELECT DISTINCT ON (domain) domain, symbol, name
            FROM kb.sp500_member
            WHERE domain IS NOT NULL
            ORDER BY domain, rank
        ),
        uk_link AS (
            SELECT DISTINCT ON (domain) domain, reg_id AS company_number, link_method, source_url
            FROM kb.domain_register_link
            WHERE registry = 'uk_company'
            ORDER BY domain, (link_method = 'reg_number_on_site') DESC, reg_id
        ),
        gl_link AS (
            SELECT DISTINCT ON (domain) domain, reg_id AS lei, link_method, source_url
            FROM kb.domain_register_link
            WHERE registry = 'gleif'
            ORDER BY domain, (link_method = 'wikidata_lei') DESC, reg_id
        ),
        cin_link AS (
            SELECT DISTINCT ON (domain) domain, reg_id AS cin, link_method, source_url
            FROM kb.domain_register_link
            WHERE registry = 'india_cin'
            ORDER BY domain, reg_id
        ),
        legal_ents AS (
            SELECT domain, jsonb_agg(ent ORDER BY registry, id) AS legal_entities
            FROM (
                SELECT DISTINCT domain, 'sec' AS registry, cik::text AS id, name
                FROM kb.sec_company WHERE domain IS NOT NULL
                UNION ALL
                SELECT DISTINCT l.domain, l.registry, l.reg_id AS id,
                       coalesce(u.name, g.legal_name, l.evidence) AS name
                FROM kb.domain_register_link l
                LEFT JOIN kb.uk_company u ON l.registry = 'uk_company' AND u.company_number = l.reg_id
                LEFT JOIN kb.gleif_company g ON l.registry = 'gleif' AND g.lei = l.reg_id
            ) sub
            CROSS JOIN LATERAL jsonb_strip_nulls(
                jsonb_build_object('registry', registry, 'id', id, 'name', name)
            ) AS ent
            GROUP BY domain
        ),
        tech_agg AS (
            SELECT domain,
                   array_agg(DISTINCT tech ORDER BY tech) FILTER (WHERE source <> 'compliance') AS techs,
                   array_agg(DISTINCT tech ORDER BY tech) FILTER (WHERE source = 'compliance') AS compliance
            FROM kb.company_tech
            GROUP BY domain
        ),
        br_agg AS (
            SELECT domain,
                   count(*)::int AS branch_count,
                   count(*) FILTER (WHERE source = 'overture' AND phone IS NOT NULL)::int AS branch_phone_count,
                   count(*) FILTER (WHERE email IS NOT NULL)::int AS br_email_count,
                   array_agg(DISTINCT country ORDER BY country) FILTER (WHERE country IS NOT NULL) AS countries
            FROM kb.company_branch
            GROUP BY domain
        ),
        pg_agg AS (
            SELECT domain,
                   coalesce(sum(jsonb_array_length(phones)), 0)::int AS pg_phones,
                   coalesce(sum(jsonb_array_length(emails)), 0)::int AS pg_emails
            FROM kb.company_page
            GROUP BY domain
        ),
        usa_agg AS (
            SELECT domain, sum(total_obligated) AS obligated, sum(award_count)::int AS awards,
                   max(link_method) AS link_method
            FROM kb.usaspending_recipient
            WHERE domain IS NOT NULL
            GROUP BY domain
        ),
        ppl_agg AS (
            SELECT domain, count(*)::int AS cnt
            FROM kb.company_person
            WHERE NOT suppressed AND end_date IS NULL
            GROUP BY domain
        )
        INSERT INTO kb.company_profile_load ({cols})
        SELECT
            u.domain,
            coalesce(sp.name, sec.name, pdl.name, ukc.name, NULLIF(split_part(hp.title, '|', 1), '')),
            coalesce(
                pdl.country,
                CASE WHEN sec.cik IS NOT NULL THEN 'united states'
                     WHEN uk.company_number IS NOT NULL THEN 'united kingdom' END
            ),
            coalesce(
                pdl.iso2,
                CASE WHEN sec.cik IS NOT NULL THEN 'US'
                     WHEN uk.company_number IS NOT NULL THEN 'GB'
                     WHEN cin.cin IS NOT NULL THEN 'IN' END
            ),
            coalesce(pdl.city, sec.city, ukc.post_town),
            coalesce(pdl.state, sec.state),
            pdl.size,
            coalesce(pdl.founded, EXTRACT(YEAR FROM ukc.incorporated)::int),
            coalesce(hp.found, false),
            hp.url,
            CASE
                WHEN lbl.real_page IS FALSE THEN 'parked_or_dead'
                WHEN hp.found AND hp.redirected_to IS NOT NULL THEN 'redirected'
                WHEN hp.found THEN 'live'
                WHEN hp.error IS NOT NULL OR hp.miss IS NOT NULL THEN 'error'
                ELSE 'not_crawled'
            END,
            coalesce(lbl.labelled_at, hp.collected_at),
            lbl.real_page,
            lbl.tech_company,
            lbl.micro_sector,
            lbl.offering,
            sp.symbol,
            sec.cik,
            sec.ticker,
            sec.sic,
            sec.sic_description,
            uk.company_number,
            ukc.status,
            ukc.incorporated,
            gl.lei,
            glc.entity_status,
            glp.direct_parent_lei,
            glp.ultimate_parent_lei,
            gp_d.legal_name,
            gp_u.legal_name,
            cin.cin,
            coalesce(le.legal_entities, '[]'::jsonb),
            sf.annual_revenue,
            sf.revenue_form,
            sf.revenue_end,
            sf.audited,
            ukf.net_assets,
            ukf.turnover,
            ukf.employees,
            usa.obligated,
            usa.awards,
            (coalesce(jsonb_array_length(hp.phones), 0) + coalesce(pga.pg_phones, 0))::int,
            coalesce(bra.branch_phone_count, 0),
            (coalesce(jsonb_array_length(hp.emails), 0) + coalesce(pga.pg_emails, 0)
             + coalesce(bra.br_email_count, 0))::int,
            coalesce(bra.branch_count, 0),
            coalesce(hir.total_open_jobs, 0),
            hir.ats,
            coalesce(ppl.cnt, 0),
            coalesce(ta.techs, '{{}}'::text[]),
            coalesce(ta.compliance, '{{}}'::text[]),
            coalesce(bra.countries, '{{}}'::text[]),
            coalesce(
                (SELECT array_agg(k ORDER BY k) FROM jsonb_object_keys(hir.departments) k),
                '{{}}'::text[]
            ),
            jsonb_strip_nulls(jsonb_build_object(
                'pdl', CASE WHEN pdl.domain IS NOT NULL THEN 'kb.pdl_company' END,
                'homepage', CASE WHEN hp.domain IS NOT NULL THEN coalesce(hp.crawl, 'homepage') END,
                'label', lbl.model,
                'sec', CASE WHEN sec.cik IS NOT NULL THEN 'kb.sec_company' END,
                'sec_fin', CASE WHEN sf.cik IS NOT NULL THEN sf.revenue_form END,
                'uk', uk.link_method,
                'uk_fin', CASE WHEN ukf.company_number IS NOT NULL THEN 'uk_accounts_ixbrl' END,
                'gleif', gl.link_method,
                'gleif_rr', CASE WHEN glp.lei IS NOT NULL THEN 'gleif_rr_2.1' END,
                'india_cin', cin.link_method,
                'usaspending', usa.link_method,
                'hiring', hir.ats,
                'people', CASE WHEN ppl.cnt > 0 THEN 'kb.company_person' END
            ))
        FROM universe u
        LEFT JOIN pdl USING (domain)
        LEFT JOIN kb.homepage hp USING (domain)
        LEFT JOIN kb.company_label lbl USING (domain)
        LEFT JOIN sp USING (domain)
        LEFT JOIN sec USING (domain)
        LEFT JOIN kb.sec_financial_latest sf ON sf.cik = sec.cik
        LEFT JOIN uk_link uk USING (domain)
        LEFT JOIN kb.uk_company ukc ON ukc.company_number = uk.company_number
        LEFT JOIN kb.uk_financials ukf ON ukf.company_number = uk.company_number
        LEFT JOIN gl_link gl USING (domain)
        LEFT JOIN kb.gleif_company glc ON glc.lei = gl.lei
        LEFT JOIN kb.gleif_parent glp ON glp.lei = gl.lei
        LEFT JOIN kb.gleif_company gp_d ON gp_d.lei = glp.direct_parent_lei
        LEFT JOIN kb.gleif_company gp_u ON gp_u.lei = glp.ultimate_parent_lei
        LEFT JOIN cin_link cin USING (domain)
        LEFT JOIN legal_ents le USING (domain)
        LEFT JOIN tech_agg ta USING (domain)
        LEFT JOIN br_agg bra USING (domain)
        LEFT JOIN pg_agg pga USING (domain)
        LEFT JOIN usa_agg usa USING (domain)
        LEFT JOIN kb.company_hiring hir USING (domain)
        LEFT JOIN ppl_agg ppl USING (domain)
    """.format(cols=", ".join(PROFILE_COLS))  # noqa: S608 - fixed static identifier tuple

    conn.execute(sql)
    # Build GIN indexes on array columns and B-tree indexes on scalar columns after data load.
    conn.execute("CREATE INDEX company_profile_techs_gin ON kb.company_profile_load USING GIN (techs)")
    conn.execute("CREATE INDEX company_profile_comp_gin ON kb.company_profile_load USING GIN (compliance)")
    conn.execute("CREATE INDEX company_profile_ctry_gin ON kb.company_profile_load USING GIN (countries)")
    conn.execute("CREATE INDEX company_profile_hiring_gin ON kb.company_profile_load USING GIN (hiring_departments)")
    conn.execute("CREATE INDEX company_profile_sic_idx ON kb.company_profile_load (sic)")
    conn.execute("CREATE INDEX company_profile_size_idx ON kb.company_profile_load (size_band)")
    conn.execute("CREATE INDEX company_profile_rev_idx ON kb.company_profile_load (annual_revenue DESC NULLS LAST)")
    conn.execute("CREATE INDEX company_profile_ukna_idx ON kb.company_profile_load (uk_net_assets DESC NULLS LAST)")
    conn.execute("CREATE INDEX company_profile_jobs_idx ON kb.company_profile_load (open_jobs DESC)")
    conn.execute("CREATE INDEX company_profile_status_idx ON kb.company_profile_load (homepage_status, real_page)")
    conn.execute("CREATE INDEX company_profile_parent_idx ON kb.company_profile_load (ultimate_parent_lei)")

    conn.execute("DROP TABLE IF EXISTS kb.company_profile")
    conn.execute("ALTER TABLE kb.company_profile_load RENAME TO company_profile")
    conn.execute("ANALYZE kb.company_profile")

    row = conn.execute("""
        SELECT count(*),
               count(*) FILTER (WHERE homepage_found),
               count(*) FILTER (WHERE real_page IS FALSE),
               count(*) FILTER (WHERE uk_company_number IS NOT NULL),
               count(*) FILTER (WHERE gleif_lei IS NOT NULL),
               count(*) FILTER (WHERE ultimate_parent_lei IS NOT NULL),
               count(*) FILTER (WHERE india_cin IS NOT NULL),
               count(*) FILTER (WHERE annual_revenue IS NOT NULL),
               count(*) FILTER (WHERE uk_net_assets IS NOT NULL),
               count(*) FILTER (WHERE usaspending_obligated IS NOT NULL)
        FROM kb.company_profile
    """).fetchone()
    return {
        "total": row[0],
        "homepage_found": row[1],
        "flagged_dead_or_parked": row[2],
        "uk_linked": row[3],
        "gleif_linked": row[4],
        "gleif_with_ultimate_parent": row[5],
        "india_cin_linked": row[6],
        "sec_revenue": row[7],
        "uk_net_assets": row[8],
        "usaspending": row[9],
        "seconds": round(time.monotonic() - t0, 1),
    }


def take_signal_snapshot(conn, snap_date: date | None = None) -> int:
    """Record Snapshot row in kb.company_signal_history for every profiled domain so future crawls yield deltas."""
    use_date = snap_date or date.today()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS kb.company_signal_history (
            domain text NOT NULL,
            snapshot_at date NOT NULL,
            homepage_found boolean NOT NULL,
            homepage_status text,
            real_page boolean,
            tech_count integer NOT NULL,
            compliance text[] NOT NULL,
            open_jobs integer NOT NULL,
            company_phone_count integer NOT NULL,
            clean_email_count integer NOT NULL,
            branch_count integer NOT NULL,
            leadership_count integer NOT NULL,
            annual_revenue double precision,
            uk_net_assets double precision,
            PRIMARY KEY (domain, snapshot_at)
        )""")
    conn.execute("ALTER TABLE kb.company_signal_history ADD COLUMN IF NOT EXISTS homepage_status text")
    conn.execute(
        """INSERT INTO kb.company_signal_history (
               domain, snapshot_at, homepage_found, homepage_status, real_page, tech_count, compliance,
               open_jobs, company_phone_count, clean_email_count, branch_count,
               leadership_count, annual_revenue, uk_net_assets
           )
           SELECT domain, %s, homepage_found, homepage_status, real_page, cardinality(techs), compliance,
                  open_jobs, company_phone_count, clean_email_count, branch_count,
                  leadership_count, annual_revenue, uk_net_assets
           FROM kb.company_profile
           ON CONFLICT (domain, snapshot_at) DO UPDATE SET
               homepage_found = EXCLUDED.homepage_found,
               homepage_status = EXCLUDED.homepage_status,
               real_page = EXCLUDED.real_page,
               tech_count = EXCLUDED.tech_count,
               compliance = EXCLUDED.compliance,
               open_jobs = EXCLUDED.open_jobs,
               company_phone_count = EXCLUDED.company_phone_count,
               clean_email_count = EXCLUDED.clean_email_count,
               branch_count = EXCLUDED.branch_count,
               leadership_count = EXCLUDED.leadership_count,
               annual_revenue = EXCLUDED.annual_revenue,
               uk_net_assets = EXCLUDED.uk_net_assets""",
        (use_date,),
    )
    return conn.execute(
        "SELECT count(*) FROM kb.company_signal_history WHERE snapshot_at = %s", (use_date,)
    ).fetchone()[0]


def benchmark_queries(conn) -> list[tuple[str, int, float]]:
    """Measure real execution time (ms) of representative B2B facet queries against kb.company_profile."""
    queries = [
        (
            "US public audited >$1B using Stripe/Cloudflare/Snowflake",
            "SELECT count(*) FROM kb.company_profile "
            "WHERE sec_audited AND annual_revenue >= 1e9 AND techs && ARRAY['Stripe','Cloudflare','Snowflake']",
        ),
        (
            "SOC 2 or ISO 27001 companies actively hiring with company phone",
            "SELECT count(*) FROM kb.company_profile "
            "WHERE compliance && ARRAY['SOC 2','ISO 27001'] AND open_jobs > 0 AND company_phone_count > 0",
        ),
        (
            "UK-linked companies with verified CH status & net assets >= £1M",
            "SELECT count(*) FROM kb.company_profile "
            "WHERE uk_company_number IS NOT NULL AND uk_net_assets >= 1000000",
        ),
        (
            "GLEIF subsidiaries rolled up by ultimate_parent_lei",
            "SELECT count(DISTINCT ultimate_parent_lei) FROM kb.company_profile "
            "WHERE ultimate_parent_lei IS NOT NULL",
        ),
    ]
    out: list[tuple[str, int, float]] = []
    for label, sql in queries:
        t0 = time.monotonic()
        cnt = conn.execute(sql).fetchone()[0]
        ms = round((time.monotonic() - t0) * 1000, 2)
        out.append((label, cnt, ms))
    return out
