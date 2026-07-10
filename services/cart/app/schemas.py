from pydantic import BaseModel


class CartItem(BaseModel):
    product_id: int
    quantity: int


class CartOut(BaseModel):
    cart_id: str
    items: list[CartItem]
