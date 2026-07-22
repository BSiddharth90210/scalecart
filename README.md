# ScaleCart

Cloud-native e-commerce platform, built as independent microservices.

## Architecture

```
                     ┌────────────┐
                     │   client   │
                     └─────┬──────┘
                           │
        ┌──────────┬───────┴───────┬────────────┐
        ▼          ▼               ▼            ▼
   ┌─────────┐ ┌────────┐    ┌──────────┐  ┌───────────┐
   │ catalog │ │  cart  │    │  orders  │  │  payments │
   │ :8001   │ │ :8002  │    │  :8003   │  │  :8004    │
   └────┬────┘ └───┬────┘    └────┬─────┘  └─────┬─────┘
        │          │               │              │
        ▼          ▼               ▼              ▼
   ┌─────────────────┐        ┌─────────┐    ┌──────────┐
   │ Postgres         │        │  Redis  │    │  Stripe  │
   │ (schema-per-svc) │◄───────┤ (cart)  │    │  (API)   │
   └─────────────────┘        └─────────┘    └──────────┘
```

- **catalog** — product data, owns the `catalog` Postgres schema
- **cart** — session/cart state in Redis, validates products against catalog
- **orders** — reads a cart, creates an order, will kick off payment
- **payments** — Stripe PaymentIntents + webhook handler with idempotent event processing

Each service is a standalone FastAPI app in its own container with its own dependencies —
you could deploy, scale, or redeploy any one of them independently.

## Running locally

```bash
docker compose up --build
```

Then:

| Service  | URL                          |
|----------|-------------------------------|
| catalog  | http://localhost:8001/docs   |
| cart     | http://localhost:8002/docs   |
| orders   | http://localhost:8003/docs   |
| payments | http://localhost:8004/docs   |

Every service exposes interactive Swagger docs at `/docs` and a `/health` check.

### Try it end to end

```bash
# 1. Create a product in the catalog
curl -X POST localhost:8001/products -H "Content-Type: application/json" -d '{
  "sku": "SKU-001", "name": "Wireless Mouse", "price_cents": 2999, "stock_qty": 50
}'

# 2. Add it to a cart (cart_id can be any string for now — a session/user id later)
curl -X POST localhost:8002/carts/my-test-cart/items -H "Content-Type: application/json" -d '{
  "product_id": 1, "quantity": 2
}'

# 3. Turn the cart into an order
curl -X POST localhost:8003/orders -H "Content-Type: application/json" -d '{
  "cart_id": "my-test-cart", "customer_email": "you@example.com"
}'
```

## Running tests

Each service will get its own test suite as it's built out. So far: **catalog**.

```bash
cd services/catalog
python -m venv venv
venv\Scripts\activate          # Windows PowerShell
pip install -r requirements.txt -r requirements-dev.txt
pytest -v
```

Tests run against an in-memory SQLite DB (no Postgres/Docker needed) so they're fast
and isolated — each test gets a clean set of tables via an autouse fixture in `conftest.py`.

## Stripe setup (for the payments service)

1. Create a free Stripe account, grab your **test mode** secret key from
   https://dashboard.stripe.com/test/apikeys
2. Put it in `services/payments/.env` as `STRIPE_SECRET_KEY`
3. For webhooks locally, install the [Stripe CLI](https://stripe.com/docs/stripe-cli) and run:
   ```bash
   stripe listen --forward-to localhost:8004/webhooks/stripe
   ```
   This prints a `whsec_...` value — put that in `STRIPE_WEBHOOK_SECRET`.

## Build roadmap (what's stubbed vs. what's next)

This skeleton gets you a running, wired-together system. Here's the natural build order from here:

- [x] **Catalog**: pagination + search filtering + pytest suite (12 tests, in-memory SQLite)
- [ ] **Catalog** (later): category model, image URLs (S3)
- [ ] **Cart**: replace the flat `1000` cent placeholder in orders with a real
      per-product price lookup against catalog
- [ ] **Orders → Payments**: wire `orders.create_order` to actually call
      `POST /payment-intents` on the payments service and return the Stripe
      `client_secret` to the client
- [ ] **Payments webhook → Orders**: on `payment_intent.succeeded`, call back
      into the orders service to flip status to `paid` (currently a TODO comment)
- [ ] **Auth**: none yet — add JWT-based auth (e.g. a lightweight `auth` service
      or middleware) once the core flow works end to end
- [ ] **Async workflows**: SQS + Lambda for email confirmation, inventory
      decrement, and receipt generation — triggered off the "order paid" event
- [ ] **AWS infra**: EC2 Auto Scaling Groups + ALB, RDS Postgres, ElastiCache
      Redis, ECS for container orchestration, S3 + CloudFront for static assets
- [ ] **CI/CD**: GitHub Actions workflow (`.github/workflows/`) to lint, test,
      build images, and deploy to ECS

We'll tackle these one at a time — local first, then layer AWS underneath once
the service logic is solid so you're not debugging Docker and IAM permissions
at the same time.

## Repo layout

```
scalecart/
├── docker-compose.yml
├── infra/
│   └── init-db.sql          # creates one Postgres schema per service
└── services/
    ├── catalog/
    ├── cart/
    ├── orders/
    └── payments/
        each with: app/, Dockerfile, requirements.txt, .env
```
