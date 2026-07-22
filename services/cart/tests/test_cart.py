"""Cart service tests.

Uses fakeredis (in-memory) for Redis and respx to mock the catalog
service HTTP calls — no Docker, no network, no external dependencies.
"""

import httpx
import respx
from httpx import Response


CATALOG_URL = "http://localhost:8001"

SAMPLE_PRODUCT = {
    "id": 1,
    "sku": "SKU-001",
    "name": "Wireless Mouse",
    "description": None,
    "price_cents": 2999,
    "currency": "usd",
    "stock_qty": 50,
}


def _catalog_product(product_id=1, **overrides):
    """Build a catalog product response payload."""
    return {**SAMPLE_PRODUCT, "id": product_id, **overrides}


def _catalog_unavailable(request):
    """Side-effect callback: simulates catalog service being down."""
    raise httpx.ConnectError("Connection refused", request=request)


# ── Health ────────────────────────────────────────────────────────────


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "service": "cart"}


# ── Get Cart ──────────────────────────────────────────────────────────


def test_get_empty_cart(client):
    resp = client.get("/carts/empty-cart")
    assert resp.status_code == 200
    body = resp.json()
    assert body["cart_id"] == "empty-cart"
    assert body["items"] == []


# ── Add Item — happy path ─────────────────────────────────────────────


def test_add_item(client):
    with respx.mock:
        respx.get(f"{CATALOG_URL}/products/1").mock(
            return_value=Response(200, json=_catalog_product(1))
        )
        resp = client.post(
            "/carts/test-cart/items", json={"product_id": 1, "quantity": 2}
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["cart_id"] == "test-cart"
    assert len(body["items"]) == 1
    assert body["items"][0]["product_id"] == 1
    assert body["items"][0]["quantity"] == 2


def test_add_item_persists_across_requests(client):
    """Items written by POST show up in a subsequent GET."""
    with respx.mock:
        respx.get(f"{CATALOG_URL}/products/1").mock(
            return_value=Response(200, json=_catalog_product(1))
        )
        client.post(
            "/carts/persist-test/items", json={"product_id": 1, "quantity": 5}
        )

    resp = client.get("/carts/persist-test")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["quantity"] == 5


def test_add_multiple_different_items(client):
    with respx.mock:
        respx.get(f"{CATALOG_URL}/products/1").mock(
            return_value=Response(200, json=_catalog_product(1))
        )
        respx.get(f"{CATALOG_URL}/products/2").mock(
            return_value=Response(200, json=_catalog_product(2, sku="SKU-002", name="Keyboard"))
        )
        client.post("/carts/multi/items", json={"product_id": 1, "quantity": 1})
        resp = client.post("/carts/multi/items", json={"product_id": 2, "quantity": 3})

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 2
    ids = {item["product_id"] for item in body["items"]}
    assert ids == {1, 2}


def test_add_same_item_merges_quantity(client):
    """Adding the same product_id twice should sum quantities, not duplicate."""
    with respx.mock:
        respx.get(f"{CATALOG_URL}/products/1").mock(
            return_value=Response(200, json=_catalog_product(1))
        )
        client.post("/carts/merge/items", json={"product_id": 1, "quantity": 2})
        resp = client.post("/carts/merge/items", json={"product_id": 1, "quantity": 3})

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["quantity"] == 5  # 2 + 3


# ── Add Item — error paths ────────────────────────────────────────────


def test_add_item_product_not_found_returns_404(client):
    with respx.mock:
        respx.get(f"{CATALOG_URL}/products/999").mock(
            return_value=Response(404, json={"detail": "Product not found"})
        )
        resp = client.post(
            "/carts/test/items", json={"product_id": 999, "quantity": 1}
        )
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_add_item_catalog_unavailable_returns_503(client):
    with respx.mock:
        respx.get(f"{CATALOG_URL}/products/1").mock(
            side_effect=_catalog_unavailable
        )
        resp = client.post(
            "/carts/test/items", json={"product_id": 1, "quantity": 1}
        )
    assert resp.status_code == 503
    assert "unavailable" in resp.json()["detail"].lower()


def test_add_item_missing_product_id_returns_422(client):
    """Pydantic validation rejects a payload without product_id."""
    resp = client.post("/carts/test/items", json={"quantity": 2})
    assert resp.status_code == 422


# ── Remove Item ───────────────────────────────────────────────────────


def test_remove_item(client):
    with respx.mock:
        respx.get(f"{CATALOG_URL}/products/1").mock(
            return_value=Response(200, json=_catalog_product(1))
        )
        client.post("/carts/rm-test/items", json={"product_id": 1, "quantity": 2})

    resp = client.delete("/carts/rm-test/items/1")
    assert resp.status_code == 200
    assert resp.json()["items"] == []


def test_remove_nonexistent_item_is_noop(client):
    """Removing an item that isn't in the cart should succeed silently."""
    resp = client.delete("/carts/empty/items/999")
    assert resp.status_code == 200
    assert resp.json()["items"] == []


# ── Clear Cart ────────────────────────────────────────────────────────


def test_clear_cart_and_verify_empty(client):
    with respx.mock:
        respx.get(f"{CATALOG_URL}/products/1").mock(
            return_value=Response(200, json=_catalog_product(1))
        )
        client.post("/carts/clear-me/items", json={"product_id": 1, "quantity": 2})

    resp = client.delete("/carts/clear-me")
    assert resp.status_code == 200
    assert resp.json()["cleared"] is True

    # Verify the cart is actually empty now
    get_resp = client.get("/carts/clear-me")
    assert get_resp.json()["items"] == []


# ── Isolation ─────────────────────────────────────────────────────────


def test_carts_are_isolated(client):
    """Different cart IDs must not leak items into each other."""
    with respx.mock:
        respx.get(f"{CATALOG_URL}/products/1").mock(
            return_value=Response(200, json=_catalog_product(1))
        )
        client.post("/carts/cart-a/items", json={"product_id": 1, "quantity": 1})

    resp_a = client.get("/carts/cart-a")
    resp_b = client.get("/carts/cart-b")

    assert len(resp_a.json()["items"]) == 1
    assert resp_b.json()["items"] == []
