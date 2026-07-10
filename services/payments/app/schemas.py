from pydantic import BaseModel


class PaymentIntentCreate(BaseModel):
    order_id: int
    amount_cents: int
    currency: str = "usd"


class PaymentIntentOut(BaseModel):
    order_id: int
    stripe_payment_intent_id: str
    client_secret: str | None = None
    status: str
