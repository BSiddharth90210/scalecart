"""Orders service tests.

Mocks three upstream services via respx:
  - cart service   (GET /carts/{id})
  - catalog service (GET /products/{id})  — real price lookup
  - payments service (POST /payment-intents) — Stripe integration

All DB operations hit in-memory SQLite (see conftest.py).
"""

import httpx
import respx
from httpx import Response


CART_URL = "http://localhost:8002"
CATALOG_URL = "http://localhost:8001"
PAYMENTS_URL = "http://localhost:8004"

SAMPLE_PRODUCT_1 = {
    "id": 1,
    "sku": "SKU-001",
    "name": "Wireless Mouse",
    "description": None,
    "price_cents": 2999,
    "currency": "usd",
    "stock_qty": 50,
}

SAMPLE_PRODUCT_2 = {
    "id": 2,
    "sku": "SKU-002",
    "name": "Mechanical Keyboard",
    "description": None,
    "price_cents": 7999,
    "currency": "usd",
    "stock_qty": 25,
}

CART_WITH_ONE_ITEM = {
    "cart_id": "test-cart",
    "items": [{"product_id": 1, "quantity": 2}],
}

CART_WITH_TWO_ITEMS = {
    "cart_id": "test-cart",
    "items": [
        {"product_id": 1, "quantity": 2},
        {"product_id": 2, "quantity": 1},
    ],
}

EMPTY_CART = {"cart_id": "test-cart", "items": []}

PAYMENT_INTENT_RESPONSE = {
    "order_id": 1,
    "stripe_payment_intent_id": "pi_test_123",
    "client_secret": "pi_test_123_secret_abc",
    "status": "requires_payment_method",
}


def _payments_unavailable(request):
    raise httpx.ConnectError("Connection refused", request=request)


def _cart_unavailable(request):
    raise httpx.ConnectError("Connection refused", request=request)


def _catalog_unavailable(request):
    raise httpx.ConnectError("Connection refused", request=request)


# ── Health ────────────────────────────────────────────────────────────


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "service": "orders"}


# ── Create Order — happy path ─────────────────────────────────────────


def test_create_order_full_flow(client):
    """Cart → catalog price lookup → DB insert → payments → client_secret."""
    with respx.mock:
        respx.get(f"{CART_URL}/carts/test-cart").mock(
            return_value=Response(200, json=CART_WITH_ONE_ITEM)
        )
        respx.get(f"{CATALOG_URL}/products/1").mock(
            return_value=Response(200, json=SAMPLE_PRODUCT_1)
        )
        respx.post(f"{PAYMENTS_URL}/payment-intents").mock(
            return_value=Response(201, json=PAYMENT_INTENT_RESPONSE)
        )
        resp = client.post(
            "/orders",
            json={"cart_id": "test-cart", "customer_email": "buyer@example.com"},
        )

    assert resp.status_code == 201
    body = resp.json()
    assert body["cart_id"] == "test-cart"
    assert body["customer_email"] == "buyer@example.com"
    assert body["status"] == "pending"
    # 2 × $29.99 = $59.98 = 5998 cents
    assert body["total_cents"] == 5998
    assert len(body["items"]) == 1
    assert body["items"][0]["unit_price_cents"] == 2999
    assert body["items"][0]["quantity"] == 2
    assert body["client_secret"] == "pi_test_123_secret_abc"


def test_create_order_multiple_items_correct_total(client):
    """Two different products: total = (2 × 2999) + (1 × 7999) = 13997."""
    with respx.mock:
        respx.get(f"{CART_URL}/carts/test-cart").mock(
            return_value=Response(200, json=CART_WITH_TWO_ITEMS)
        )
        respx.get(f"{CATALOG_URL}/products/1").mock(
            return_value=Response(200, json=SAMPLE_PRODUCT_1)
        )
        respx.get(f"{CATALOG_URL}/products/2").mock(
            return_value=Response(200, json=SAMPLE_PRODUCT_2)
        )
        respx.post(f"{PAYMENTS_URL}/payment-intents").mock(
            return_value=Response(201, json=PAYMENT_INTENT_RESPONSE)
        )
        resp = client.post(
            "/orders",
            json={"cart_id": "test-cart", "customer_email": "buyer@example.com"},
        )

    assert resp.status_code == 201
    assert resp.json()["total_cents"] == 13997
    assert len(resp.json()["items"]) == 2


def test_create_order_payments_down_still_creates_order(client):
    """If payments service is unreachable, order is still created (pending)
    but client_secret is None — client can retry payment later."""
    with respx.mock:
        respx.get(f"{CART_URL}/carts/test-cart").mock(
            return_value=Response(200, json=CART_WITH_ONE_ITEM)
        )
        respx.get(f"{CATALOG_URL}/products/1").mock(
            return_value=Response(200, json=SAMPLE_PRODUCT_1)
        )
        respx.post(f"{PAYMENTS_URL}/payment-intents").mock(
            side_effect=_payments_unavailable
        )
        resp = client.post(
            "/orders",
            json={"cart_id": "test-cart", "customer_email": "buyer@example.com"},
        )

    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "pending"
    assert body["client_secret"] is None
    # Order still exists in DB
    get_resp = client.get(f"/orders/{body['id']}")
    assert get_resp.status_code == 200


# ── Create Order — error paths ────────────────────────────────────────


def test_create_order_empty_cart_returns_400(client):
    with respx.mock:
        respx.get(f"{CART_URL}/carts/test-cart").mock(
            return_value=Response(200, json=EMPTY_CART)
        )
        resp = client.post(
            "/orders",
            json={"cart_id": "test-cart", "customer_email": "buyer@example.com"},
        )
    assert resp.status_code == 400
    assert "empty" in resp.json()["detail"].lower()


def test_create_order_cart_service_unavailable(client):
    with respx.mock:
        respx.get(f"{CART_URL}/carts/test-cart").mock(
            side_effect=_cart_unavailable
        )
        resp = client.post(
            "/orders",
            json={"cart_id": "test-cart", "customer_email": "buyer@example.com"},
        )
    assert resp.status_code == 503


def test_create_order_product_not_in_catalog(client):
    """Product was in cart but has since been removed from catalog."""
    with respx.mock:
        respx.get(f"{CART_URL}/carts/test-cart").mock(
            return_value=Response(200, json=CART_WITH_ONE_ITEM)
        )
        respx.get(f"{CATALOG_URL}/products/1").mock(
            return_value=Response(404)
        )
        resp = client.post(
            "/orders",
            json={"cart_id": "test-cart", "customer_email": "buyer@example.com"},
        )
    assert resp.status_code == 400
    assert "no longer available" in resp.json()["detail"].lower()


def test_create_order_catalog_unavailable(client):
    with respx.mock:
        respx.get(f"{CART_URL}/carts/test-cart").mock(
            return_value=Response(200, json=CART_WITH_ONE_ITEM)
        )
        respx.get(f"{CATALOG_URL}/products/1").mock(
            side_effect=_catalog_unavailable
        )
        resp = client.post(
            "/orders",
            json={"cart_id": "test-cart", "customer_email": "buyer@example.com"},
        )
    assert resp.status_code == 503


# ── Get Order ─────────────────────────────────────────────────────────


def test_get_order_not_found(client):
    resp = client.get("/orders/999")
    assert resp.status_code == 404


# ── Update Order Status (PATCH) ──────────────────────────────────────


def test_update_order_status(client):
    """Create an order, then flip it to 'paid' via PATCH."""
    with respx.mock:
        respx.get(f"{CART_URL}/carts/test-cart").mock(
            return_value=Response(200, json=CART_WITH_ONE_ITEM)
        )
        respx.get(f"{CATALOG_URL}/products/1").mock(
            return_value=Response(200, json=SAMPLE_PRODUCT_1)
        )
        respx.post(f"{PAYMENTS_URL}/payment-intents").mock(
            return_value=Response(201, json=PAYMENT_INTENT_RESPONSE)
        )
        create_resp = client.post(
            "/orders",
            json={"cart_id": "test-cart", "customer_email": "buyer@example.com"},
        )

    order_id = create_resp.json()["id"]
    patch_resp = client.patch(
        f"/orders/{order_id}/status", json={"status": "paid"}
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["status"] == "paid"

    # Verify the status persisted
    get_resp = client.get(f"/orders/{order_id}")
    assert get_resp.json()["status"] == "paid"


def test_update_order_status_not_found(client):
    resp = client.patch("/orders/999/status", json={"status": "paid"})
    assert resp.status_code == 404
