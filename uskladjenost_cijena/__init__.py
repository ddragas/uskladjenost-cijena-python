"""Python SDK for the Usklađenost cijena API.

    from uskladjenost_cijena import Client

    api = Client("pc_live_...")
    item = api.items.upsert("SKU-1", merchant_id=m, kind="product", name="Deterdžent 3 kg")
    api.prices.record_by_external("SKU-1", regular_price_minor=1250, location_code="PU-01")
    print(api.compliance.by_external("SKU-1")["data"]["anchor_display"]["label"])
"""

from .client import ApiError, Client
from .webhooks import sign, verify, event

__all__ = ["Client", "ApiError", "sign", "verify", "event"]
__version__ = "1.0.0"
