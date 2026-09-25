import json

import pytest
import responses

from uskladjenost_cijena import ApiError, Client

BASE = "https://example.test"


@pytest.fixture
def api():
    return Client("pc_test_abc", BASE)


@responses.activate
def test_the_token_and_the_user_agent_travel_with_every_call(api):
    responses.get(f"{BASE}/api/v1/ping", json={"data": {"pong": True, "tenant": "Firma"}})
    assert api.ping()["data"]["tenant"] == "Firma"
    request = responses.calls[0].request
    assert request.headers["Authorization"] == "Bearer pc_test_abc"
    assert request.headers["User-Agent"].startswith("uskladjenost-cijena-python/")


@responses.activate
def test_items_are_written_and_read_by_the_callers_ids(api):
    responses.put(f"{BASE}/api/v1/items/SKU%2F1", json={"data": {"id": "i1", "offer_id": "o1"}}, status=201)
    result = api.items.upsert("SKU/1", merchant_id="m1", kind="product", name="Deterdžent")
    assert result["data"]["offer_id"] == "o1" and result["_status"] == 201
    assert json.loads(responses.calls[0].request.body)["name"] == "Deterdžent"

    responses.get(f"{BASE}/api/v1/items", json={"data": [{"id": "i1"}], "next_cursor": "i1"})
    responses.get(f"{BASE}/api/v1/items", json={"data": [{"id": "i2"}], "next_cursor": None})
    assert [i["id"] for i in api.items.all(merchant_id="m1", limit=1)] == ["i1", "i2"]
    assert responses.calls[2].request.params == {"merchant_id": "m1", "limit": "1", "cursor": "i1"}

    responses.get(f"{BASE}/api/v1/items/SKU-1", json={"data": {"id": "i1"}})
    api.items.get("SKU-1", merchant_id="m1")
    assert responses.calls[3].request.params == {"merchant_id": "m1"}

    responses.post(f"{BASE}/api/v1/items/bulk", json={"data": [], "summary": {"created": 2}})
    assert api.items.bulk([{"external_id": "a", "name": "A"}, {"external_id": "b", "name": "B"}])["summary"]["created"] == 2


@responses.activate
def test_prices_go_in_by_offer_or_by_the_callers_id(api):
    responses.post(f"{BASE}/api/v1/offers/o1/price-events", json={"data": {"id": 7}}, status=201)
    api.prices.record("o1", regular_price_minor=1250, idempotency_key="k-1")
    assert responses.calls[0].request.headers["Idempotency-Key"] == "k-1"
    assert json.loads(responses.calls[0].request.body) == {"regular_price_minor": 1250}

    responses.post(f"{BASE}/api/v1/prices/by-external/SKU-1", json={"data": {"id": 8, "scope": {"location_code": "PU-01"}}}, status=201)
    result = api.prices.record_by_external("SKU-1", regular_price_minor=1250, effective_price_minor=990, location_code="PU-01")
    assert result["data"]["scope"]["location_code"] == "PU-01"
    assert json.loads(responses.calls[1].request.body) == {"regular_price_minor": 1250, "effective_price_minor": 990, "location_code": "PU-01"}
    assert "Idempotency-Key" not in responses.calls[1].request.headers

    responses.get(f"{BASE}/api/v1/offers/o1/price-events", json={"data": [{"id": 8}, {"id": 7}], "next_cursor": None})
    assert len(api.prices.history("o1", since="2026-09-01T00:00:00Z", limit=50)["data"]) == 2
    assert responses.calls[2].request.params == {"since": "2026-09-01T00:00:00Z", "limit": "50"}

    responses.post(f"{BASE}/api/v1/price-events/bulk", json={"summary": {"created": 1}})
    api.prices.bulk([{"offer_id": "o1", "regular_price_minor": 100}])


@responses.activate
def test_compliance_publications_imports_and_webhooks(api):
    responses.get(f"{BASE}/api/v1/compliance/by-external/SKU-1", json={"data": {"anchor_display": {"label": "Cijena na dan 10. 9. 2026.: 22,00 €"}}})
    assert "22,00" in api.compliance.by_external("SKU-1", location_code="PU-01", locale="hr")["data"]["anchor_display"]["label"]
    assert responses.calls[0].request.params == {"location_code": "PU-01", "locale": "hr"}

    responses.post(f"{BASE}/api/v1/compliance/query", json={"data": []})
    api.compliance.query(["o1", "o2"], locale="en")
    assert json.loads(responses.calls[1].request.body) == {"offer_ids": ["o1", "o2"], "locale": "en"}

    responses.get(f"{BASE}/api/v1/publication-scopes", json={"data": [{"scope_id": "s1", "stale": False}]})
    assert api.publications.scopes()["data"][0]["stale"] is False
    responses.post(f"{BASE}/api/v1/publication-scopes/s1/publish", status=202)
    assert api.publications.publish("s1")["_status"] == 202

    responses.post(f"{BASE}/api/v1/imports", json={"data": {"id": 5, "status": "checked", "preview": {"new": 3}}}, status=202)
    result = api.imports.upload("m1", "items_prices", "sifra;naziv;cijena\nA;Artikl;1,00\n", "cjenik.csv", dry_run=True, on_conflict="update")
    assert result["data"]["preview"]["new"] == 3
    body = responses.calls[4].request.body
    assert b'name="dry_run"' in body and b"\r\n1\r\n" in body and b'filename="cjenik.csv"' in body

    responses.post(f"{BASE}/api/v1/webhooks", json={"data": {"id": "w1", "secret": "whsec_x"}}, status=201)
    assert api.webhooks.create("https://shop.test/hook", ["publication.succeeded"])["data"]["secret"] == "whsec_x"
    responses.delete(f"{BASE}/api/v1/webhooks/w1", status=204)
    assert api.webhooks.delete("w1")["_status"] == 204


@responses.activate
def test_a_refusal_becomes_an_error_with_the_apis_code_and_details(api):
    responses.put(f"{BASE}/api/v1/items/x", json={"error": {"code": "validation", "message": "The item could not be saved.", "details": {"name": ["Missing."]}}}, status=422)
    with pytest.raises(ApiError) as e:
        api.items.upsert("x")
    assert e.value.code == "validation" and e.value.status == 422 and e.value.details["name"] == ["Missing."]

    responses.post(f"{BASE}/api/v1/offers/o1/price-events", json={"error": {"code": "insufficient_scope", "message": "This token lacks the prices:write scope."}}, status=403)
    with pytest.raises(ApiError, match="prices:write"):
        api.prices.record("o1", regular_price_minor=1)
