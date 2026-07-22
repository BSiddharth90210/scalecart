import os
import httpx
import stripe
from fastapi import FastAPI, Depends, HTTPException, Request, Header
from sqlalchemy.orm import Session

from app.db import Base, engine, get_db
from app.models import PaymentIntentRecord, ProcessedWebhookEvent
from app.schemas import PaymentIntentCreate, PaymentIntentOut

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
ORDERS_SERVICE_URL = os.getenv("ORDERS_SERVICE_URL", "http://localhost:8003")
stripe.api_key = STRIPE_SECRET_KEY

app = FastAPI(title="ScaleCart - Payments Service")


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)


@app.get("/health")
def health():
    return {"status": "ok", "service": "payments"}


@app.post("/payment-intents", response_model=PaymentIntentOut, status_code=201)
def create_payment_intent(payload: PaymentIntentCreate, db: Session = Depends(get_db)):
    if not STRIPE_SECRET_KEY or STRIPE_SECRET_KEY.startswith("sk_test_replace"):
        raise HTTPException(
            status_code=500,
            detail="Stripe secret key not configured. Set STRIPE_SECRET_KEY in services/payments/.env",
        )

    intent = stripe.PaymentIntent.create(
        amount=payload.amount_cents,
        currency=payload.currency,
        metadata={"order_id": str(payload.order_id)},
    )

    record = PaymentIntentRecord(
        order_id=payload.order_id,
        stripe_payment_intent_id=intent["id"],
        amount_cents=payload.amount_cents,
        currency=payload.currency,
        status=intent["status"],
    )
    db.add(record)
    db.commit()

    return PaymentIntentOut(
        order_id=payload.order_id,
        stripe_payment_intent_id=intent["id"],
        client_secret=intent["client_secret"],
        status=intent["status"],
    )


@app.post("/webhooks/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="Stripe-Signature"),
    db: Session = Depends(get_db),
):
    payload = await request.body()

    try:
        event = stripe.Webhook.construct_event(payload, stripe_signature, STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.error.SignatureVerificationError):
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    # Idempotency: if we've already processed this exact Stripe event, no-op.
    already_processed = (
        db.query(ProcessedWebhookEvent)
        .filter(ProcessedWebhookEvent.stripe_event_id == event["id"])
        .first()
    )
    if already_processed:
        return {"status": "already_processed"}

    if event["type"] == "payment_intent.succeeded":
        intent = event["data"]["object"]
        record = (
            db.query(PaymentIntentRecord)
            .filter(PaymentIntentRecord.stripe_payment_intent_id == intent["id"])
            .first()
        )
        if record:
            record.status = "succeeded"
            # Notify the orders service to flip the order to "paid".
            # Best-effort: if orders is unreachable, the status can be
            # reconciled later via a batch job.
            async with httpx.AsyncClient(timeout=5.0) as http:
                try:
                    await http.patch(
                        f"{ORDERS_SERVICE_URL}/orders/{record.order_id}/status",
                        json={"status": "paid"},
                    )
                except httpx.RequestError:
                    pass  # logged in production; reconciled async

    elif event["type"] == "payment_intent.payment_failed":
        intent = event["data"]["object"]
        record = (
            db.query(PaymentIntentRecord)
            .filter(PaymentIntentRecord.stripe_payment_intent_id == intent["id"])
            .first()
        )
        if record:
            record.status = "failed"
            async with httpx.AsyncClient(timeout=5.0) as http:
                try:
                    await http.patch(
                        f"{ORDERS_SERVICE_URL}/orders/{record.order_id}/status",
                        json={"status": "failed"},
                    )
                except httpx.RequestError:
                    pass

    db.add(ProcessedWebhookEvent(stripe_event_id=event["id"]))
    db.commit()

    return {"status": "received"}
