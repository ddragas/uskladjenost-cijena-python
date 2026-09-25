"""Webhook deliveries: X-PC-Signature: v1=HMAC-SHA256(secret, timestamp + "." + body)
with X-PC-Timestamp; deliveries older than the tolerance are refused."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any, Dict, Mapping, Optional, Union


def sign(secret: str, timestamp: str, body: Union[str, bytes]) -> str:
    raw = body if isinstance(body, bytes) else body.encode("utf-8")
    return "v1=" + hmac.new(secret.encode("utf-8"), timestamp.encode("utf-8") + b"." + raw, hashlib.sha256).hexdigest()


def verify(secret: str, signature_header: str, timestamp_header: str, body: Union[str, bytes], tolerance_seconds: int = 300, now: Optional[int] = None) -> bool:
    if not timestamp_header.isdigit():
        return False
    if abs((now if now is not None else int(time.time())) - int(timestamp_header)) > tolerance_seconds:
        return False
    expected = sign(secret, timestamp_header, body)
    return any(hmac.compare_digest(expected, candidate.strip()) for candidate in signature_header.split(","))


def event(secret: str, headers: Mapping[str, str], body: Union[str, bytes], tolerance_seconds: int = 300) -> Dict[str, Any]:
    """The verified event from a request's headers and raw body; raises ValueError when the signature does not hold."""
    lower = {k.lower(): v for k, v in headers.items()}
    if not verify(secret, lower.get("x-pc-signature", ""), lower.get("x-pc-timestamp", ""), body, tolerance_seconds):
        raise ValueError("The webhook signature does not hold.")
    data = json.loads(body)
    if not isinstance(data, dict):
        return {}
    data.setdefault("event", lower.get("x-pc-event"))
    data.setdefault("event_id", lower.get("x-pc-event-id"))
    return data
