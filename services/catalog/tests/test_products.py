def _make_product(client, sku="SKU-001", name="Wireless Mouse", price_cents=2999, stock_qty=10):
    return client.post(
        "/products",
        json={
            "sku": sku,
            "name": name,
            "price_cents": price_cents,
            "stock_qty": stock_qty,
        },
    )


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "service": "catalog"}


def test_create_product(client):
    resp = _make_product(client)
    assert resp.status_code == 201
    body = resp.json()
    assert body["sku"] == "SKU-001"
    assert body["name"] == "Wireless Mouse"
    assert body["price_cents"] == 2999
    assert "id" in body


def test_create_product_duplicate_sku_returns_409(client):
    _make_product(client, sku="SKU-DUPE")
    resp = _make_product(client, sku="SKU-DUPE")
    assert resp.status_code == 409


def test_get_product_by_id(client):
    created = _make_product(client).json()
    resp = client.get(f"/products/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["sku"] == "SKU-001"


def test_get_product_not_found(client):
    resp = client.get("/products/999999")
    assert resp.status_code == 404


def test_list_products_empty(client):
    resp = client.get("/products")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_products_returns_all(client):
    _make_product(client, sku="SKU-A", name="Keyboard")
    _make_product(client, sku="SKU-B", name="Monitor")
    resp = client.get("/products")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_search_filters_by_name_case_insensitive(client):
    _make_product(client, sku="SKU-A", name="Wireless Keyboard")
    _make_product(client, sku="SKU-B", name="USB Monitor")
    resp = client.get("/products", params={"search": "keyboard"})
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) == 1
    assert results[0]["sku"] == "SKU-A"


def test_search_filters_by_sku(client):
    _make_product(client, sku="ABC-123", name="Widget")
    _make_product(client, sku="XYZ-999", name="Gadget")
    resp = client.get("/products", params={"search": "abc"})
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) == 1
    assert results[0]["sku"] == "ABC-123"


def test_pagination_limit(client):
    for i in range(5):
        _make_product(client, sku=f"SKU-{i}", name=f"Product {i}")
    resp = client.get("/products", params={"limit": 2})
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_pagination_skip(client):
    for i in range(5):
        _make_product(client, sku=f"SKU-{i}", name=f"Product {i}")
    page_1 = client.get("/products", params={"skip": 0, "limit": 2}).json()
    page_2 = client.get("/products", params={"skip": 2, "limit": 2}).json()
    assert {p["id"] for p in page_1}.isdisjoint({p["id"] for p in page_2})


def test_pagination_limit_out_of_range_rejected(client):
    resp = client.get("/products", params={"limit": 500})
    assert resp.status_code == 422
