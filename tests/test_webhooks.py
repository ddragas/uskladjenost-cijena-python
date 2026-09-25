import time

import pytest

from uskladjenost_cijena import webhooks


def test_a_fresh_delivery_verifies_and_a_stale_or_forged_one_does_not():
    body = '{"event":"publication.succeeded","data":{"scope_id":"s1"}}'
    ts = str(int(time.time()))
    sig = webhooks.sign("whsec_x", ts, body)
    assert webhooks.verify("whsec_x", sig, ts, body)
    assert webhooks.verify("whsec_x", "v1=deadbeef," + sig, ts, body)
    assert not webhooks.verify("whsec_y", sig, ts, body)
    assert not webhooks.verify("whsec_x", sig, ts, body + " ")
    assert not webhooks.verify("whsec_x", sig, str(int(time.time()) - 301), body)
    assert not webhooks.verify("whsec_x", sig, "abc", body)

    event = webhooks.event("whsec_x", {"X-PC-Signature": sig, "X-PC-Timestamp": ts, "X-PC-Event-Id": "e1"}, body.encode())
    assert event["data"]["scope_id"] == "s1" and event["event_id"] == "e1" and event["event"] == "publication.succeeded"

    with pytest.raises(ValueError):
        webhooks.event("whsec_x", {"X-PC-Signature": "v1=nope", "X-PC-Timestamp": ts}, body)
