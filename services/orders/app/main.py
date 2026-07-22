import os
import httpx
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import Base, engine, get_db
from app.models import Order, OrderItem, OrderStatus
from app.schemas import OrderCreate, OrderOut, OrderStatusUpdate

CART_SERVICE_URL = os.getenv("CART_SERVICE_URL", "http://localhost:8002")
CATALOG_SERVICE_URL = os.getenv("CATALOG_SERVICE_URL", "http://localhost:8001")
PAYMENTS_SERVICE_URL = os.getenv("PAYMENTS_SERVICE_URL", "http://localhost:8004")

app = FastAPI(title="ScaleCart - Orders Service")


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)


@app.get("/health")
def health():
    return {"status": "ok", "service": "orders"}


@app.get("/orders/{order_id}", response_model=OrderOut)
def get_order(order_id: int, db: Session = Depends(get_db)):
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@app.patch("/orders/{order_id}/status", response_model=OrderOut)
def update_order_status(
    order_id: int,
    payload: OrderStatusUpdate,
    db: Session = Depends(get_db),
):
    """Update order status — called by the payments webhook on success/failure."""
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    order.status = payload.status
    db.commit()
    db.refresh(order)
    return order


@app.post("/orders", response_model=OrderOut, status_code=201)
async def create_order(payload: OrderCreate, db: Session = Depends(get_db)):
    async with httpx.AsyncClient(timeout=5.0) as http:
        # ── 1. Fetch the cart ────────────────────────────────────────
        try:
            cart_resp = await http.get(
                f"{CART_SERVICE_URL}/carts/{payload.cart_id}"
            )
        except httpx.RequestError:
            raise HTTPException(
                status_code=503, detail="Cart service unavailable"
            )

        if cart_resp.status_code != 200:
            raise HTTPException(status_code=502, detail="Could not fetch cart")

        cart_data = cart_resp.json()
        if not cart_data["items"]:
            raise HTTPException(status_code=400, detail="Cart is empty")

        # ── 2. Look up real prices from the catalog ──────────────────
        order = Order(
            cart_id=payload.cart_id,
            customer_email=payload.customer_email,
            status=OrderStatus.pending,
            total_cents=0,
            currency="usd",
        )
        total = 0

        for item in cart_data["items"]:
            try:
                prod_resp = await http.get(
                    f"{CATALOG_SERVICE_URL}/products/{item['product_id']}"
                )
            except httpx.RequestError:
                raise HTTPException(
                    status_code=503, detail="Catalog service unavailable"
                )

            if prod_resp.status_code == 404:
                raise HTTPException(
                    status_code=400,
                    detail=f"Product {item['product_id']} no longer available",
                )

            product = prod_resp.json()
            unit_price = product["price_cents"]
            total += unit_price * item["quantity"]
            order.items.append(
                OrderItem(
                    product_id=item["product_id"],
                    quantity=item["quantity"],
                    unit_price_cents=unit_price,
                )
            )

        order.total_cents = total
        db.add(order)
        db.commit()
        db.refresh(order)

        # ── 3. Create Stripe PaymentIntent (best-effort) ─────────────
        # If the payments service is down, the order still exists in
        # "pending" status.  The client can retry payment later.
        client_secret = None
        try:
            pay_resp = await http.post(
                f"{PAYMENTS_SERVICE_URL}/payment-intents",
                json={
                    "order_id": order.id,
                    "amount_cents": order.total_cents,
                    "currency": order.currency,
                },
                timeout=10.0,
            )
            if pay_resp.status_code == 201:
                client_secret = pay_resp.json().get("client_secret")
        except httpx.RequestError:
            pass  # order persisted; payment can be retried

    # Build the response with the transient client_secret attached
    out = OrderOut.model_validate(order, from_attributes=True)
    return out.model_copy(update={"client_secret": client_secret})
