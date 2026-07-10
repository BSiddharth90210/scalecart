from pydantic import BaseModel, ConfigDict
from app.models import OrderStatus


class OrderCreate(BaseModel):
    cart_id: str
    customer_email: str


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
