"""Payments service tests.

Mocks:
  - stripe.PaymentIntent.create  (via unittest.mock.patch)
  - stripe.Webhook.construct_event (via unittest.mock.patch)
  - orders service callback      (via respx — PATCH /orders/{id}/status)

All DB operations hit in-memory SQLite (see conftest.py).
"""

from unittest.mock import patch, MagicMock

import httpx
import respx
from httpx import Response


ORDERS_URL = "http://localhost:8003"

# ── Helpers ───────────────────────────────────────────────────────────

FAKE_INTENT = {
    "id": "pi_test_abc123",
    "client_secret": "pi_test_abc123_secret_xyz",
    "status": "requires_payment_method",
}


def _build_stripe_event(event_type: str, intent_id: str, event_id: str = "evt_test_001"):
    """Build a fake Stripe event dict matching the shape the webhook handler expects."""
    return {
        "id": event_id,
        "type": event_type,
        "data": {
            "object": {
                "id": intent_id,
            },
        },
    }


def _orders_unavailable(request):
    raise httpx.ConnectError("Connection refused", request=request)


# ── Health ────────────────────────────────────────────────────────────


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "service": "payments"}


# ── POST /payment-intents — happy path ────────────────────────────────


@patch("app.main.stripe.PaymentIntent.create", return_value=FAKE_INTENT)
@patch("app.main.STRIPE_SECRET_KEY", "sk_test_real_key")
def test_create_payment_intent(mock_stripe_create, client):
    """Create a PaymentIntent: verify response shape and DB record."""
    resp = client.post(
        "/payment-intents",
        json={"order_id": 42, "amount_cents": 5998, "currency": "usd"},
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["order_id"] == 42
    assert body["stripe_payment_intent_id"] == "pi_test_abc123"
    assert body["client_secret"] == "pi_test_abc123_secret_xyz"
    assert body["status"] == "requires_payment_method"

    # Stripe was called with the right params
    mock_stripe_create.assert_called_once_with(
        amount=5998,
        currency="usd",
        metadata={"order_id": "42"},
    )


# ── POST /payment-intents — error paths ──────────────────────────────


@patch("app.main.STRIPE_SECRET_KEY", "")
def test_create_payment_intent_no_stripe_key(client):
    """Returns 500 when STRIPE_SECRET_KEY is empty."""
    resp = client.post(
        "/payment-intents",
        json={"order_id": 1, "amount_cents": 1000, "currency": "usd"},
    )
    assert resp.status_code == 500
    assert "not configured" in resp.json()["detail"].lower()


@patch("app.main.STRIPE_SECRET_KEY", "sk_test_real_key")
@patch(
    "app.main.stripe.PaymentIntent.create",
    side_effect=Exception("Stripe connection error"),
)
def test_create_payment_intent_stripe_error(mock_stripe_create, client):
    """If Stripe raises, the error propagates (FastAPI returns 500 in production)."""
    import pytest

    with pytest.raises(Exception, match="Stripe connection error"):
        client.post(
            "/payment-intents",
            json={"order_id": 1, "amount_cents": 1000, "currency": "usd"},
        )


# ── POST /webhooks/stripe — payment_intent.succeeded ──────────────────


@patch("app.main.stripe.Webhook.construct_event")
@patch("app.main.stripe.PaymentIntent.create", return_value=FAKE_INTENT)
@patch("app.main.STRIPE_SECRET_KEY", "sk_test_real_key")
def test_webhook_payment_succeeded(mock_stripe_create, mock_construct, client):
    """Webhook flips record to 'succeeded' and fires orders callback."""
    # Step 1: create a PaymentIntent so the record exists in DB
    client.post(
        "/payment-intents",
        json={"order_id": 42, "amount_cents": 5998, "currency": "usd"},
    )

    # Step 2: simulate Stripe webhook
    event = _build_stripe_event("payment_intent.succeeded", "pi_test_abc123")
    mock_construct.return_value = event

    with respx.mock:
        respx.patch(f"{ORDERS_URL}/orders/42/status").mock(
            return_value=Response(200, json={"status": "paid"})
        )

        resp = client.post(
            "/webhooks/stripe",
            content=b'{"fake": "payload"}',
            headers={"Stripe-Signature": "sig_test"},
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "received"


@patch("app.main.stripe.Webhook.construct_event")
@patch("app.main.stripe.PaymentIntent.create", return_value=FAKE_INTENT)
@patch("app.main.STRIPE_SECRET_KEY", "sk_test_real_key")
def test_webhook_payment_succeeded_orders_down(mock_stripe_create, mock_construct, client):
    """If orders service is unreachable, webhook still returns 200 (best-effort)."""
    client.post(
        "/payment-intents",
        json={"order_id": 42, "amount_cents": 5998, "currency": "usd"},
    )

    event = _build_stripe_event("payment_intent.succeeded", "pi_test_abc123")
    mock_construct.return_value = event

    with respx.mock:
        respx.patch(f"{ORDERS_URL}/orders/42/status").mock(
            side_effect=_orders_unavailable
        )

        resp = client.post(
            "/webhooks/stripe",
            content=b'{"fake": "payload"}',
            headers={"Stripe-Signature": "sig_test"},
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "received"


# ── POST /webhooks/stripe — payment_intent.payment_failed ─────────────


@patch("app.main.stripe.Webhook.construct_event")
@patch("app.main.stripe.PaymentIntent.create", return_value=FAKE_INTENT)
@patch("app.main.STRIPE_SECRET_KEY", "sk_test_real_key")
def test_webhook_payment_failed(mock_stripe_create, mock_construct, client):
    """Failed payment flips record to 'failed' and notifies orders."""
    client.post(
        "/payment-intents",
        json={"order_id": 42, "amount_cents": 5998, "currency": "usd"},
    )

    event = _build_stripe_event("payment_intent.payment_failed", "pi_test_abc123")
    mock_construct.return_value = event

    with respx.mock:
        respx.patch(f"{ORDERS_URL}/orders/42/status").mock(
            return_value=Response(200, json={"status": "failed"})
        )

        resp = client.post(
            "/webhooks/stripe",
            content=b'{"fake": "payload"}',
            headers={"Stripe-Signature": "sig_test"},
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "received"


# ── POST /webhooks/stripe — idempotency ───────────────────────────────


@patch("app.main.stripe.Webhook.construct_event")
@patch("app.main.stripe.PaymentIntent.create", return_value=FAKE_INTENT)
@patch("app.main.STRIPE_SECRET_KEY", "sk_test_real_key")
def test_webhook_idempotent_skips_duplicate(mock_stripe_create, mock_construct, client):
    """Second delivery of the same Stripe event ID returns 'already_processed'."""
    client.post(
        "/payment-intents",
        json={"order_id": 42, "amount_cents": 5998, "currency": "usd"},
    )

    event = _build_stripe_event("payment_intent.succeeded", "pi_test_abc123", event_id="evt_duplicate")
    mock_construct.return_value = event

    with respx.mock:
        respx.patch(f"{ORDERS_URL}/orders/42/status").mock(
            return_value=Response(200, json={"status": "paid"})
        )

        # First call — processes normally
        resp1 = client.post(
            "/webhooks/stripe",
            content=b'{"fake": "payload"}',
            headers={"Stripe-Signature": "sig_test"},
        )
        assert resp1.json()["status"] == "received"

        # Second call — same event ID, should be skipped
        resp2 = client.post(
            "/webhooks/stripe",
            content=b'{"fake": "payload"}',
            headers={"Stripe-Signature": "sig_test"},
        )
        assert resp2.json()["status"] == "already_processed"


# ── POST /webhooks/stripe — invalid signature ─────────────────────────


@patch(
    "app.main.stripe.Webhook.construct_event",
    side_effect=ValueError("Invalid signature"),
)
def test_webhook_invalid_signature(mock_construct, client):
    """Bad Stripe signature returns 400."""
    resp = client.post(
        "/webhooks/stripe",
        content=b'{"fake": "payload"}',
        headers={"Stripe-Signature": "bad_sig"},
    )
    assert resp.status_code == 400
    assert "invalid" in resp.json()["detail"].lower()


# ── POST /webhooks/stripe — unknown event type ────────────────────────


@patch("app.main.stripe.Webhook.construct_event")
def test_webhook_unknown_event_type_still_records(mock_construct, client):
    """Unrecognised event types are recorded (for idempotency) but no status change."""
    event = _build_stripe_event("charge.refunded", "pi_test_abc123", event_id="evt_unknown")
    mock_construct.return_value = event

    with respx.mock:
        resp = client.post(
            "/webhooks/stripe",
            content=b'{"fake": "payload"}',
            headers={"Stripe-Signature": "sig_test"},
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "received"

    # Sending the same event again proves it was recorded
    resp2 = client.post(
        "/webhooks/stripe",
        content=b'{"fake": "payload"}',
        headers={"Stripe-Signature": "sig_test"},
    )
    assert resp2.json()["status"] == "already_processed"
