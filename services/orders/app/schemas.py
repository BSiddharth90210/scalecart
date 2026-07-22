from pydantic import BaseModel, ConfigDict
from app.models import OrderStatus


class OrderCreate(BaseModel):
    cart_id: str
    customer_email: str


class OrderStatusUpdate(BaseModel):
    status: OrderStatus


class OrderItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    product_id: int
    quantity: int
    unit_price_cents: int


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    cart_id: str
    customer_email: str
    status: OrderStatus
    total_cents: int
    currency: str
    items: list[OrderItemOut]
    # Populated on creation only — the Stripe client_secret needed by the
    # frontend to complete payment via Stripe.js.  None when fetching
    # an existing order (the secret is stored in the payments service).
    client_secret: str | None = None
