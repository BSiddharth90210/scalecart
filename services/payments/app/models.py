from sqlalchemy import Column, Integer, String, DateTime, func
from app.db import Base


class PaymentIntentRecord(Base):
    __tablename__ = "payment_intents"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, nullable=False, index=True)
    stripe_payment_intent_id = Column(String(255), unique=True, nullable=False)
    amount_cents = Column(Integer, nullable=False)
    currency = Column(String(3), nullable=False, default="usd")
    status = Column(String(32), nullable=False, default="requires_payment_method")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ProcessedWebhookEvent(Base):
    """
    Tracks Stripe event IDs we've already handled so a retried/duplicate
    webhook delivery can't double-process a payment (idempotency).
    """
    __tablename__ = "processed_webhook_events"

    id = Column(Integer, primary_key=True, index=True)
    stripe_event_id = Column(String(255), unique=True, nullable=False, index=True)
    processed_at = Column(DateTime(timezone=True), server_default=func.now())
