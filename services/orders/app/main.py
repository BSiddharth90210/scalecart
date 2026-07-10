import os
import httpx
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import Base, engine, get_db
from app.models import Order, OrderItem, OrderStatus
from app.schemas import OrderCreate, OrderOut

CART_SERVICE_URL = os.getenv("CART_SERVICE_URL", "http://localhost:8002")
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


@app.post("/orders", response_model=OrderOut, status_code=201)
async def create_order(payload: OrderCreate, db: Session = Depends(get_db)):
    # 1. Pull the cart from the cart service.
    async with httpx.AsyncClient() as client:
        try:
            cart_resp = await client.get(f"{CART_SERVICE_URL}/carts/{payload.cart_id}", timeout=5.0)
        except httpx.RequestError:
            raise HTTPException(status_code=503, detail="Cart service unavailable")

    if cart_resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Could not fetch cart")

    cart_data = cart_resp.json()
    if not cart_data["items"]:
        raise HTTPException(status_code=400, detail="Cart is empty")

    # NOTE: this is a placeholder price lookup. Next step: fetch real prices
    # from the catalog service per item instead of a flat stub value.
    order = Order(
        cart_id=payload.cart_id,
        customer_email=payload.customer_email,
        status=OrderStatus.pending,
        total_cents=0,
        currency="usd",
    )
    total = 0
    for item in cart_data["items"]:
        unit_price_cents = 1000  # TODO: replace with real catalog price lookup
        total += unit_price_cents * item["quantity"]
        order.items.append(
            OrderItem(
                product_id=item["product_id"],
                quantity=item["quantity"],
                unit_price_cents=unit_price_cents,
            )
        )
    order.total_cents = total

    db.add(order)
    db.commit()
    db.refresh(order)

    # 2. TODO: call payments service to create a Stripe PaymentIntent here,
    #    then let the Stripe webhook flip order.status to "paid".

    return order
