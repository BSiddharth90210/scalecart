import os
import json
import httpx
import redis
from fastapi import FastAPI, HTTPException

from app.schemas import CartItem, CartOut

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CATALOG_SERVICE_URL = os.getenv("CATALOG_SERVICE_URL", "http://localhost:8001")
CART_TTL_SECONDS = int(os.getenv("CART_TTL_SECONDS", "86400"))

app = FastAPI(title="ScaleCart - Cart Service")
r = redis.Redis.from_url(REDIS_URL, decode_responses=True)


def _key(cart_id: str) -> str:
    return f"cart:{cart_id}"


@app.get("/health")
def health():
    return {"status": "ok", "service": "cart"}


@app.get("/carts/{cart_id}", response_model=CartOut)
def get_cart(cart_id: str):
    raw = r.get(_key(cart_id))
    items = json.loads(raw) if raw else []
    return CartOut(cart_id=cart_id, items=items)


@app.post("/carts/{cart_id}/items", response_model=CartOut)
async def add_item(cart_id: str, item: CartItem):
    # Validate the product exists via the catalog service before adding it.
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{CATALOG_SERVICE_URL}/products/{item.product_id}", timeout=5.0)
        except httpx.RequestError:
            raise HTTPException(status_code=503, detail="Catalog service unavailable")
    if resp.status_code == 404:
        raise HTTPException(status_code=404, detail="Product not found in catalog")

    raw = r.get(_key(cart_id))
    items = json.loads(raw) if raw else []

    for existing in items:
        if existing["product_id"] == item.product_id:
            existing["quantity"] += item.quantity
            break
    else:
        items.append(item.model_dump())

    r.set(_key(cart_id), json.dumps(items), ex=CART_TTL_SECONDS)
    return CartOut(cart_id=cart_id, items=items)


@app.delete("/carts/{cart_id}/items/{product_id}", response_model=CartOut)
def remove_item(cart_id: str, product_id: int):
    raw = r.get(_key(cart_id))
    items = json.loads(raw) if raw else []
    items = [i for i in items if i["product_id"] != product_id]
    r.set(_key(cart_id), json.dumps(items), ex=CART_TTL_SECONDS)
    return CartOut(cart_id=cart_id, items=items)


@app.delete("/carts/{cart_id}")
def clear_cart(cart_id: str):
    r.delete(_key(cart_id))
    return {"cart_id": cart_id, "cleared": True}
