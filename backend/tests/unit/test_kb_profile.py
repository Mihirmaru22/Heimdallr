"""Unit tests for kb.profile schema consistency and static benchmark queries."""

from __future__ import annotations

from app.kb import profile


def test_profile_cols_match_create_table_definition():
    seen_sql: list[str] = []

    class DummyConn:
        def execute(self, sql: str) -> None:
            seen_sql.append(sql)

    profile._create_profile_table(DummyConn(), "company_profile_load")
    assert len(seen_sql) == 1
    body = seen_sql[0].split("(", 1)[1].rsplit(")", 1)[0]
    cols = [line.strip().split()[0] for line in body.splitlines() if line.strip()]
    assert tuple(cols[:-1]) == profile.PROFILE_COLS
    assert cols[-1] == "updated_at"
