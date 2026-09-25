# Usklađenost cijena – Python SDK

Python klijent za API servisa [Usklađenost cijena](https://uskladjenost-cijena.com): sidrene cijene i javni strojno čitljiv cjenik po NN 101/2026. Pokriva cijeli API: trgovce, lokacije i kanale, katalog, cijene, odluke o usklađenosti, objave cjenika, uvoz datoteka i webhookove, uz provjeru potpisa webhook isporuka.

```bash
pip install uskladjenost-cijena
```

Python 3.9+, jedina ovisnost je `requests`. API token (`pc_live_…` ili `pc_test_…`) izdajete u aplikaciji pod **API pristup**; token nosi opsege (scopes).

## Brzi početak

```python
from uskladjenost_cijena import Client

api = Client(os.environ["PC_TOKEN"])

# 1. Artikl po vašoj šifri (catalog:write); odgovor nosi offer_id
item = api.items.upsert("SKU-1", merchant_id=merchant_id, kind="product", name="Deterdžent 3 kg", barcode="3859000000001", fmcg_category="cleaning")

# 2. Cijena po vašoj šifri, bez offer_id-a (prices:write); iznosi u centima
api.prices.record_by_external("SKU-1", regular_price_minor=1250, effective_price_minor=990, location_code="PU-01", idempotency_key="order-42-line-1")

# 3. Što ispisati uz cijenu (compliance:read)
decision = api.compliance.by_external("SKU-1", location_code="PU-01")
print(decision["data"]["anchor_display"]["label"])  # "Cijena na dan 10. 9. 2026.: 12,50 €" ili None
```

## Sve metode

| Resurs | Metoda | Poziv | Opseg |
|---|---|---|---|
| — | `ping()` | `GET /api/v1/ping` | — |
| `merchants` | `list()` | `GET /merchants` | catalog:read |
| | `upsert(key, **data)` | `PUT /merchants/{key}` | catalog:write |
| | `locations(merchant_id)` / `channels(merchant_id)` | `GET /merchants/{id}/locations` / `channels` | catalog:read |
| | `upsert_location(merchant_id, code, **data)` / `upsert_channel(...)` | `PUT /merchants/{id}/locations/{code}` | catalog:write |
| `items` | `list(**filters)` / `all(**filters)` | `GET /items` (kursor) | catalog:read |
| | `get(external_id, merchant_id=None, source_system=None)` | `GET /items/{id}` | catalog:read |
| | `upsert(external_id, **data)` / `bulk(items)` | `PUT /items/{id}` / `POST /items/bulk` | catalog:write |
| `prices` | `record(offer_id, idempotency_key=None, **event)` | `POST /offers/{id}/price-events` | prices:write |
| | `record_by_external(external_id, location_code=..., **event)` | `POST /prices/by-external/{id}` | prices:write |
| | `bulk(events)` | `POST /price-events/bulk` | prices:write |
| | `history(offer_id, since=None, cursor=None, limit=None)` | `GET /offers/{id}/price-events` | prices:read |
| `offers` | `get(offer_id)` | `GET /offers/{id}` | prices:read |
| `compliance` | `for_offer(offer_id, at=None, locale=None)` | `GET /offers/{id}/compliance` | compliance:read |
| | `by_external(external_id, **scope)` | `GET /compliance/by-external/{id}` | compliance:read |
| | `query(offer_ids, at=None, locale=None)` | `POST /compliance/query` | compliance:read |
| | `list(**filters)` / `all(**filters)` | `GET /compliance` | compliance:read |
| `publications` | `scopes()` / `status(scope_id)` | `GET /publication-scopes` | publications:read |
| | `publish(scope_id)` | `POST /publication-scopes/{id}/publish` | publications:manage |
| `imports` | `upload(merchant_id, type, file, filename, on_conflict=None, dry_run=None)` | `POST /imports` | imports:write |
| | `get(import_id)` | `GET /imports/{id}` | imports:write |
| `webhooks` | `list()` / `create(url, events, description=None)` / `test(id)` / `delete(id)` | `/webhooks` | webhooks:manage |

Svaka metoda vraća dekodirani JSON kao `dict` (`data`, `next_cursor`, `summary`…) plus `_status`. Odbijanje API-ja je `ApiError` s `code` (npr. `validation`, `not_found`, `ambiguous`, `insufficient_scope`), `status` i `details`.

## Webhookovi

```python
from uskladjenost_cijena import webhooks

event = webhooks.event(secret, request.headers, request.get_data())  # ValueError ako potpis ne drži
if event["event"] == "publication.failed":
    ...
```

## Razvoj

```bash
pip install -e .[dev] && pytest
```

Dokumentacija API-ja: `https://uskladjenost-cijena.com/api/docs` i `/api/swagger`. Licenca MIT, © Info Media d.o.o.

## Ostali SDK-ovi i dodaci

Ista obitelj za isti API, svaki u svom repozitoriju:

- [uskladjenost-cijena-php](https://github.com/ddragas/uskladjenost-cijena-php) – PHP SDK (Composer `infomedia/uskladjenost-cijena-php`)
- [uskladjenost-cijena-js](https://github.com/ddragas/uskladjenost-cijena-js) – JavaScript/TypeScript SDK (`uskladjenost-cijena`)
- [uskladjenost-cijena-woocommerce](https://github.com/ddragas/uskladjenost-cijena-woocommerce) – WooCommerce dodatak
- [uskladjenost-cijena-shopify](https://github.com/ddragas/uskladjenost-cijena-shopify) – Shopify custom app
- [uskladjenost-cijena-prestashop](https://github.com/ddragas/uskladjenost-cijena-prestashop) – PrestaShop 8 modul
