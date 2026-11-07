from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
import requests

from app.catalog_sources import companies_house, overture, usaspending
from app.catalog_sources.public_api import PublicApiError, PublicApiSession, retry_after_seconds


def _response(status: int, body: dict | None = None, headers: dict | None = None) -> requests.Response:
    response = requests.Response()
    response.status_code = status
    response.headers.update(headers or {})
    response._content = json.dumps(body or {}).encode()
    response.url = "https://source.example/api"
    return response


class StubSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.headers = {}
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)


def test_retry_after_supports_seconds_and_http_date():
    assert retry_after_seconds("5") == 5
    assert retry_after_seconds("Wed, 21 Oct 2015 07:28:00 GMT",
                               now=datetime(2015, 10, 21, 7, 27, 55, tzinfo=UTC)) == 5
    assert retry_after_seconds("invalid") is None


def test_public_api_retries_429_after_retry_after_and_keeps_one_session(monkeypatch):
    session = StubSession([_response(429, headers={"Retry-After": "3"}), _response(200, {"ok": True})])
    waited = []
    monkeypatch.setattr("app.catalog_sources.public_api.time.sleep", waited.append)
    monkeypatch.setattr("app.catalog_sources.public_api.random.uniform", lambda _a, _b: 0)
    client = PublicApiSession(session=session, max_retries=1, min_interval_seconds=0)
    assert client.get_json("https://source.example/api") == {"ok": True}
    assert waited == [3]
    assert len(session.calls) == 2
    assert session.headers["User-Agent"].startswith("Heimdallr/")


def test_public_api_fails_fast_on_403():
    session = StubSession([_response(403)])
    client = PublicApiSession(session=session, max_retries=4, min_interval_seconds=0)
    with pytest.raises(PublicApiError, match="403"):
        client.get_json("https://source.example/api")
    assert len(session.calls) == 1


def test_public_api_enforces_shared_session_request_spacing(monkeypatch):
    session = StubSession([_response(200, {"ok": True}), _response(200, {"ok": True})])
    clock = iter([10.0, 10.0, 10.1, 10.5])
    waited = []
    monkeypatch.setattr("app.catalog_sources.public_api.time.monotonic", lambda: next(clock))
    monkeypatch.setattr("app.catalog_sources.public_api.time.sleep", waited.append)
    client = PublicApiSession(session=session, min_interval_seconds=0.5)
    assert client.get_json("https://source.example/one") == {"ok": True}
    assert client.get_json("https://source.example/two") == {"ok": True}
    assert waited == [pytest.approx(0.4)]


def test_companies_house_claims_preserve_raw_values_and_official_provenance():
    company = {"number": "01234567", "url": "https://find-and-update.company-information.service.gov.uk/company/01234567",
               "profile": {"company_name": "Example Limited", "company_number": "01234567",
                           "company_status": "active", "date_of_creation": "2001-02-03",
                           "sic_codes": ["62020"], "registered_office_address": {"locality": "London"}}}
    claims = companies_house.claims_for(company)
    by_field = {claim["field_key"]: claim for claim in claims}
    assert by_field["registered_name"]["value"] == "Example Limited"
    assert by_field["registered_office_address"]["raw_value"] == {"locality": "London"}
    assert by_field["company_number"]["verified_direct"] is True
    assert by_field["company_number"]["source_record_id"] == "01234567"
    assert "license not asserted" in by_field["company_number"]["source_license"].lower()


def test_usaspending_uses_recipient_filter_and_award_only_fields():
    class Client:
        def post_json(self, url, *, json_body):
            assert url == usaspending.API
            assert json_body["filters"]["recipient_search_text"] == ["Example Corporation"]
            assert "award_type_codes" in json_body["filters"]
            return {"results": [{"Recipient Name": "Example Corporation", "Award ID": "A-1"}]}

    rows = usaspending.search_awards("Example Corporation", client=Client())
    assert rows[0]["Award ID"] == "A-1"
    assert "uses_technology" not in rows[0]


def test_overture_requires_bounded_region_and_reads_geojson(tmp_path: Path):
    command = overture.download_command((-71.2, 42.2, -70.9, 42.5), tmp_path / "places.geojson")
    assert command[:2] == ["overturemaps", "download"]
    assert "--type=place" in command and "--bbox=-71.2,42.2,-70.9,42.5" in command
    with pytest.raises(ValueError, match="Bounding box"):
        overture.download_command((-181, 42, -70, 43), tmp_path / "bad.geojson")
    path = tmp_path / "places.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": [{"properties": {"name": "Example"}}]}))
    assert list(overture._read_features(path))[0]["properties"]["name"] == "Example"
