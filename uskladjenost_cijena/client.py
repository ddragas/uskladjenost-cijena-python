from __future__ import annotations

from typing import IO, Any, Dict, Iterator, List, Optional, Union

import requests

__version__ = "1.0.0"

Json = Dict[str, Any]


class ApiError(Exception):
    """The API refused or could not answer.

    `code` is the API's own code (validation, not_found, ambiguous,
    insufficient_scope, ...), `status` the HTTP status, `details` the
    per-field messages of a 422.
    """

    def __init__(self, code: str, message: str, status: int, details: Optional[Json] = None):
        super().__init__(f"{code} ({status}): {message}")
        self.code = code
        self.status = status
        self.details = details or {}
        self.api_message = message


def _clean(params: Json) -> Json:
    return {k: v for k, v in params.items() if v is not None}


class Client:
    """The Usklađenost cijena API from Python. Every method returns the decoded
    JSON body (a dict) plus `_status`; every refusal raises ApiError."""

    def __init__(self, token: str, base_url: str = "https://uskladjenost-cijena.com", timeout: float = 30.0, session: Optional[requests.Session] = None):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": f"uskladjenost-cijena-python/{__version__}",
        })
        self.merchants = Merchants(self)
        self.items = Items(self)
        self.prices = Prices(self)
        self.offers = Offers(self)
        self.compliance = Compliance(self)
        self.publications = Publications(self)
        self.imports = Imports(self)
        self.webhooks = Webhooks(self)

    def ping(self) -> Json:
        return self.request("GET", "/api/v1/ping")

    def request(self, method: str, path: str, *, params: Optional[Json] = None, json: Optional[Json] = None, headers: Optional[Dict[str, str]] = None, files: Any = None, data: Any = None) -> Json:
        try:
            response = self.session.request(method, self.base_url + path, params=_clean(params or {}) or None, json=json, headers=headers, files=files, data=data, timeout=self.timeout)
        except requests.RequestException as e:
            raise ApiError("transport", str(e), 0) from e
        if response.status_code >= 400:
            raise _refusal(response)
        if not response.content:
            return {"_status": response.status_code}
        try:
            body = response.json()
        except ValueError:
            raise ApiError("malformed", "The API answered with something that is not JSON.", response.status_code)
        if not isinstance(body, dict):
            body = {"data": body}
        body["_status"] = response.status_code
        return body


def _refusal(response: requests.Response) -> ApiError:
    status = response.status_code
    try:
        body = response.json()
    except ValueError:
        body = {}
    error = body.get("error") if isinstance(body, dict) and isinstance(body.get("error"), dict) else {}
    code = error.get("code") or {401: "unauthenticated", 403: "forbidden", 404: "not_found", 429: "rate_limited"}.get(status, f"http_{status}")
    message = error.get("message") or (body.get("message") if isinstance(body, dict) else None) or f"HTTP {status}"
    details = error.get("details") if isinstance(error.get("details"), dict) else (body.get("errors") if isinstance(body, dict) and isinstance(body.get("errors"), dict) else {})
    return ApiError(str(code), str(message), status, details)


def _quote(value: str) -> str:
    from urllib.parse import quote

    return quote(value, safe="")


class _Resource:
    def __init__(self, client: Client):
        self._client = client


class Merchants(_Resource):
    """Merchants, their locations and sales channels. Scopes catalog:read / catalog:write."""

    def list(self) -> Json:
        return self._client.request("GET", "/api/v1/merchants")

    def upsert(self, external_key: str, **data: Any) -> Json:
        return self._client.request("PUT", f"/api/v1/merchants/{_quote(external_key)}", json=data)

    def locations(self, merchant_id: str) -> Json:
        return self._client.request("GET", f"/api/v1/merchants/{_quote(merchant_id)}/locations")

    def upsert_location(self, merchant_id: str, code: str, **data: Any) -> Json:
        return self._client.request("PUT", f"/api/v1/merchants/{_quote(merchant_id)}/locations/{_quote(code)}", json=data)

    def channels(self, merchant_id: str) -> Json:
        return self._client.request("GET", f"/api/v1/merchants/{_quote(merchant_id)}/channels")

    def upsert_channel(self, merchant_id: str, code: str, **data: Any) -> Json:
        return self._client.request("PUT", f"/api/v1/merchants/{_quote(merchant_id)}/channels/{_quote(code)}", json=data)


class Items(_Resource):
    """The catalogue, by your own ids. Scopes catalog:read / catalog:write."""

    def list(self, **filters: Any) -> Json:
        """One page. Filters: merchant_id, kind, active, q, updated_since, cursor, limit."""
        return self._client.request("GET", "/api/v1/items", params=filters)

    def all(self, **filters: Any) -> Iterator[Json]:
        """Every item, page after page."""
        cursor = None
        while True:
            page = self.list(cursor=cursor, **filters)
            yield from page.get("data", [])
            cursor = page.get("next_cursor")
            if not cursor:
                return

    def get(self, external_id: str, merchant_id: Optional[str] = None, source_system: Optional[str] = None) -> Json:
        return self._client.request("GET", f"/api/v1/items/{_quote(external_id)}", params={"merchant_id": merchant_id, "source_system": source_system})

    def upsert(self, external_id: str, **data: Any) -> Json:
        """Create or update by your own id; the answer carries offer_id."""
        return self._client.request("PUT", f"/api/v1/items/{_quote(external_id)}", json=data)

    def bulk(self, items: List[Json]) -> Json:
        """Up to 500 rows, each an item plus external_id."""
        return self._client.request("POST", "/api/v1/items/bulk", json={"items": list(items)})


class Prices(_Resource):
    """Price events: append-only, idempotent. Scopes prices:write / prices:read."""

    def record(self, offer_id: str, *, idempotency_key: Optional[str] = None, **event: Any) -> Json:
        """Record a price on an offer (regular_price_minor, effective_price_minor, price_from, price_to_minor, valid_from, ...)."""
        return self._client.request("POST", f"/api/v1/offers/{_quote(offer_id)}/price-events", json=event, headers=_idem(idempotency_key))

    def record_by_external(self, external_id: str, *, idempotency_key: Optional[str] = None, merchant_id: Optional[str] = None, source_system: Optional[str] = None, location_code: Optional[str] = None, channel_code: Optional[str] = None, **event: Any) -> Json:
        """Record a price by your own product id; no offer id needed."""
        body = dict(event)
        body.update(_clean({"merchant_id": merchant_id, "source_system": source_system, "location_code": location_code, "channel_code": channel_code}))
        return self._client.request("POST", f"/api/v1/prices/by-external/{_quote(external_id)}", json=body, headers=_idem(idempotency_key))

    def bulk(self, events: List[Json]) -> Json:
        """Up to 1000 rows, each an event plus offer_id (and optionally idempotency_key)."""
        return self._client.request("POST", "/api/v1/price-events/bulk", json={"events": list(events)})

    def history(self, offer_id: str, since: Optional[str] = None, cursor: Optional[int] = None, limit: Optional[int] = None) -> Json:
        """The offer's history, newest first; `data` and `next_cursor`."""
        return self._client.request("GET", f"/api/v1/offers/{_quote(offer_id)}/price-events", params={"since": since, "cursor": cursor, "limit": limit})


def _idem(key: Optional[str]) -> Optional[Dict[str, str]]:
    return {"Idempotency-Key": key} if key else None


class Offers(_Resource):
    """One offer: the item, the scope, the price in force. Scope prices:read."""

    def get(self, offer_id: str) -> Json:
        return self._client.request("GET", f"/api/v1/offers/{_quote(offer_id)}")


class Compliance(_Resource):
    """What to print next to a price. Scope compliance:read."""

    def for_offer(self, offer_id: str, at: Optional[str] = None, locale: Optional[str] = None) -> Json:
        return self._client.request("GET", f"/api/v1/offers/{_quote(offer_id)}/compliance", params={"at": at, "locale": locale})

    def by_external(self, external_id: str, **scope: Any) -> Json:
        """By your own product id. Scope: merchant_id, source_system, location_code, channel_code, at, locale."""
        return self._client.request("GET", f"/api/v1/compliance/by-external/{_quote(external_id)}", params=scope)

    def query(self, offer_ids: List[str], at: Optional[str] = None, locale: Optional[str] = None) -> Json:
        """Decisions for up to 500 offers."""
        return self._client.request("POST", "/api/v1/compliance/query", json=_clean({"offer_ids": list(offer_ids), "at": at, "locale": locale}))

    def list(self, **filters: Any) -> Json:
        """One page of every active offer's decision. Filters: merchant_id, location_id, sales_channel_id, kind, needs_review, updated_since, cursor, limit."""
        return self._client.request("GET", "/api/v1/compliance", params=filters)

    def all(self, **filters: Any) -> Iterator[Json]:
        cursor = None
        while True:
            page = self.list(cursor=cursor, **filters)
            yield from page.get("data", [])
            cursor = page.get("next_cursor")
            if not cursor:
                return


class Publications(_Resource):
    """The public price lists. Scopes publications:read / publications:manage."""

    def scopes(self) -> Json:
        return self._client.request("GET", "/api/v1/publication-scopes")

    def status(self, scope_id: str) -> Json:
        return self._client.request("GET", f"/api/v1/publication-scopes/{_quote(scope_id)}/status")

    def publish(self, scope_id: str) -> Json:
        return self._client.request("POST", f"/api/v1/publication-scopes/{_quote(scope_id)}/publish")


class Imports(_Resource):
    """CSV / XLSX uploads with a dry run. Scope imports:write."""

    def upload(self, merchant_id: str, type: str, file: Union[bytes, str, IO[bytes]], filename: str, *, on_conflict: Optional[str] = None, dry_run: Optional[bool] = None) -> Json:
        """type: items_prices, historical_prices, anchors, locations, availability. The answer carries counts, per-row errors and preview."""
        content = file.encode("utf-8") if isinstance(file, str) else file
        data = _clean({"merchant_id": merchant_id, "type": type, "on_conflict": on_conflict, "dry_run": None if dry_run is None else ("1" if dry_run else "0")})
        return self._client.request("POST", "/api/v1/imports", data=data, files={"file": (filename, content)})

    def get(self, import_id: int) -> Json:
        return self._client.request("GET", f"/api/v1/imports/{int(import_id)}")


class Webhooks(_Resource):
    """Webhook endpoints. Scope webhooks:manage. Verify deliveries with uskladjenost_cijena.webhooks."""

    def list(self) -> Json:
        return self._client.request("GET", "/api/v1/webhooks")

    def create(self, url: str, events: List[str], description: Optional[str] = None) -> Json:
        """Add an endpoint; the answer carries the secret once."""
        return self._client.request("POST", "/api/v1/webhooks", json=_clean({"url": url, "events": list(events), "description": description}))

    def test(self, endpoint_id: str) -> Json:
        return self._client.request("POST", f"/api/v1/webhooks/{_quote(endpoint_id)}/test")

    def delete(self, endpoint_id: str) -> Json:
        return self._client.request("DELETE", f"/api/v1/webhooks/{_quote(endpoint_id)}")
