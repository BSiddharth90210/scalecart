from pydantic import BaseModel, ConfigDict


class ProductCreate(BaseModel):
    sku: str
    name: str
    description: str | None = None
    price_cents: int
    currency: str = "usd"
    stock_qty: int = 0


class ProductOut(ProductCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
