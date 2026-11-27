"""Unit tests for SEC EDGAR XBRL companyfacts extraction."""

from __future__ import annotations

import json
import zipfile

from app.kb import sec_facts


def test_extract_company_facts_filters_q4_slices_computes_yoy_and_marks_audited():
    payload = {
        "cik": 320193,
        "entityName": "Apple Inc.",
        "facts": {
            "dei": {
                "EntityNumberOfEmployees": {
                    "units": {"persons": [{"end": "2026-09-26", "val": 164000, "form": "10-K", "filed": "2026-11-03"}]}
                }
            },
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {
                        "USD": [
                            # 90-day Q4 slice filed inside 10-K must be rejected so it never overwrites annual revenue.
                            {"start": "2026-06-28", "end": "2026-09-26", "val": 100, "fy": 2026, "fp": "FY",
                             "form": "10-K", "filed": "2026-11-03"},
                            {"start": "2025-09-28", "end": "2026-09-26", "val": 440, "fy": 2026, "fp": "FY",
                             "form": "10-K", "filed": "2026-11-03"},
                            {"start": "2024-09-29", "end": "2025-09-27", "val": 400, "fy": 2025, "fp": "FY",
                             "form": "10-K", "filed": "2025-11-01"},
                            {"start": "2026-03-29", "end": "2026-06-27", "val": 105, "fy": 2026, "fp": "Q3",
                             "form": "10-Q", "filed": "2026-07-31"},
                        ]
                    }
                },
                "Assets": {
                    "units": {
                        "USD": [
                            {"end": "2026-09-26", "val": 4000, "fy": 2026, "fp": "FY",
                             "form": "10-K", "filed": "2026-11-03"},
                        ]
                    }
                },
            },
        },
    }
    facts, latest = sec_facts.extract_company_facts(payload)
    assert latest is not None
    row = dict(zip(sec_facts.LATEST_COLUMNS, latest, strict=True))
    assert row["cik"] == 320193
    assert row["annual_revenue"] == 440.0
    assert row["prior_annual_revenue"] == 400.0
    assert row["revenue_yoy_pct"] == 10.0
    assert row["revenue_form"] == "10-K" and row["audited"] is True
    assert row["assets"] == 4000.0 and row["employees"] == 164000
    # 90-day 10-K Q4 slice is excluded; 10-K FY26, 10-K FY25, and 10-Q Q3 remain.
    rev_vals = sorted(f[13] for f in facts if f[1] == "revenue")
    assert rev_vals == [105.0, 400.0, 440.0]


def test_iter_zip_handles_ifrs_foreign_filer(tmp_path):
    zpath = tmp_path / "companyfacts.zip"
    with zipfile.ZipFile(zpath, "w") as z:
        z.writestr("CIK0000937966.json", json.dumps({
            "cik": 937966,
            "entityName": "ASML Holding N.V.",
            "facts": {
                "ifrs-full": {
                    "Revenue": {
                        "units": {"EUR": [
                            {"start": "2025-01-01", "end": "2025-12-31", "val": 28000000000, "fy": 2025,
                             "fp": "FY", "form": "20-F", "filed": "2026-02-15"},
                        ]}
                    }
                }
            },
        }))
    out = list(sec_facts.iter_zip(zpath))
    assert len(out) == 1
    row = dict(zip(sec_facts.LATEST_COLUMNS, out[0][1], strict=True))
    assert row["revenue_currency"] == "EUR" and row["revenue_form"] == "20-F" and row["audited"] is True
