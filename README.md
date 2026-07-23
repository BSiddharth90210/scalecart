<p align="center">
  <h1 align="center">🛒 ScaleCart</h1>
  <p align="center">
    <strong>Cloud-Native E-Commerce Platform — Microservices, Stripe, Docker, AWS</strong>
  </p>
  <p align="center">
    <a href="#architecture">Architecture</a> •
    <a href="#tech-stack">Tech Stack</a> •
    <a href="#quick-start">Quick Start</a> •
    <a href="#api-reference">API Reference</a> •
    <a href="#design-decisions">Design Decisions</a> •
    <a href="#development-progress">Progress</a>
  </p>
  <p align="center">
    <a href="https://github.com/BSiddharth90210/scalecart/actions/workflows/ci.yml">
      <img src="https://github.com/BSiddharth90210/scalecart/actions/workflows/ci.yml/badge.svg" alt="CI">
    </a>
  </p>
</p>

<br/>

## What Is This?

ScaleCart is a **production-grade e-commerce backend** built from scratch as independent microservices. It handles the full purchase lifecycle — browsing products, building a cart, placing orders, and processing payments via Stripe — with each concern isolated in its own deployable service.

This isn't a monolith split into folders. Each service has its own **Dockerfile, dependencies, database schema, and API surface**. You can deploy, scale, or redeploy any one of them without touching the others.

**Key engineering highlights:**

- **4 independent FastAPI microservices** communicating over HTTP, each containerized with Docker
- **Stripe payment processing** with webhook-driven order confirmation and idempotent event handling (no duplicate charges)
- **Schema-per-service isolation** on a shared PostgreSQL instance — cheap for dev, same pattern scales to separate RDS instances in prod
- **Redis-backed cart** with TTL-based session expiry and cross-service product validation
- **46-test pytest suite** across 4 services — catalog (12), cart (13), orders (11), payments (10) — all against in-memory backends
- **GitHub Actions CI** running all tests in parallel on every push
- **Docker Compose** orchestration with health checks, dependency ordering, and hot-reload dev volumes

---

## Architecture

```
                        ┌─────────────────┐
                        │     Client      │
                        └────────┬────────┘
                                 │
          ┌──────────────┬───────┴────────┬──────────────┐
          ▼              ▼                ▼              ▼
   ┌────────────┐  ┌──────────┐   ┌────────────┐  ┌────────────┐
   │  Catalog   │  │   Cart   │   │   Orders   │  │  Payments  │
   │  :8001     │  │  :8002   │   │   :8003    │  │   :8004    │
   │            │  │          │   │            │  │            │
   │ Products   │  │ Add/Rmv  │   │ Create     │  │ Stripe     │
   │ Search     │  │ Validate │   │ Track      │  │ Intents    │
   │ Paginate   │  │ Session  │   │ Fulfill    │  │ Webhooks   │
   └─────┬──────┘  └────┬─────┘   └─────┬──────┘  └─────┬──────┘
         │               │               │               │
         ▼               ▼               ▼               ▼
   ┌───────────────────────┐       ┌──────────┐    ┌───────────┐
   │   PostgreSQL 16       │       │  Redis 7 │    │  Stripe   │
   │   (schema-per-svc)    │◄──────┤  (cart   │    │  (API)    │
   │                       │       │   cache) │    │           │
   │  ┌─────────┐          │       └──────────┘    └───────────┘
   │  │ catalog │          │
   │  │ orders  │          │
   │  │payments │          │
   │  └─────────┘          │
   └───────────────────────┘
```

### Service Responsibilities

| Service | Port | Data Store | Responsibilities |
|---------|------|------------|-----------------|
| **Catalog** | 8001 | PostgreSQL (`catalog` schema) | Product CRUD, search (case-insensitive, name + SKU), pagination with configurable limits |
| **Cart** | 8002 | Redis (key-per-cart, 24h TTL) | Add/remove items, quantity merging, validates products exist via catalog service |
| **Orders** | 8003 | PostgreSQL (`orders` schema) | Pulls cart contents, creates order with line items, tracks status lifecycle (`pending` → `paid` → `fulfilled`) |
| **Payments** | 8004 | PostgreSQL (`payments` schema) | Creates Stripe PaymentIntents, processes webhooks idempotently (tracks processed event IDs to prevent duplicate handling) |

### Inter-Service Communication

```
Cart ──validates product──► Catalog    (GET /products/{id})
Orders ──fetches cart──────► Cart      (GET /carts/{cart_id})
Orders ──price lookup──────► Catalog   (GET /products/{id})
Orders ──creates payment───► Payments  (POST /payment-intents)
Payments ──confirms order──► Orders    (PATCH /orders/{id}/status via webhook)
```

---

## Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| **Language** | Python 3.13 | Async-first with type hints for API contracts |
| **Framework** | FastAPI 0.115 | Auto-generated OpenAPI docs, Pydantic validation, dependency injection |
| **ORM** | SQLAlchemy 2.0 | Declarative models, schema-per-service isolation |
| **Database** | PostgreSQL 16 | ACID transactions for orders/payments, schema isolation per service |
| **Cache** | Redis 7 | Sub-millisecond cart reads, TTL-based session expiry |
| **Payments** | Stripe API | PaymentIntents for SCA compliance, webhook-driven confirmation |
| **Containers** | Docker + Compose | Service isolation, reproducible builds, health-checked orchestration |
| **Testing** | pytest + httpx | In-memory SQLite for fast isolated tests, TestClient for API assertions |
| **CI/CD** | GitHub Actions | _Planned: lint → test → build → deploy to ECS_ |
| **Cloud** | AWS (EC2, RDS, ElastiCache, SQS, Lambda, ECS, S3, CloudFront) | _Planned: horizontally scalable production deployment_ |

---

## Quick Start

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (or Docker Engine + Compose)
- A [Stripe test-mode API key](https://dashboard.stripe.com/test/apikeys) (free, for the payments service)

### 1. Clone & Run

```bash
git clone https://github.com/BSiddharth90210/scalecart.git
cd scalecart
docker compose up --build
```

This starts **6 containers** — 4 services + PostgreSQL + Redis — with health checks and dependency ordering. All services hot-reload from mounted volumes.

### 2. Explore the APIs

Every service exposes interactive Swagger docs:

| Service | Swagger UI | Health Check |
|---------|-----------|-------------|
| Catalog | [localhost:8001/docs](http://localhost:8001/docs) | [localhost:8001/health](http://localhost:8001/health) |
| Cart | [localhost:8002/docs](http://localhost:8002/docs) | [localhost:8002/health](http://localhost:8002/health) |
| Orders | [localhost:8003/docs](http://localhost:8003/docs) | [localhost:8003/health](http://localhost:8003/health) |
| Payments | [localhost:8004/docs](http://localhost:8004/docs) | [localhost:8004/health](http://localhost:8004/health) |

### 3. Try the Full Purchase Flow

```bash
# 1. Create a product
curl -X POST localhost:8001/products \
  -H "Content-Type: application/json" \
  -d '{"sku": "SKU-001", "name": "Wireless Mouse", "price_cents": 2999, "stock_qty": 50}'

# 2. Search for it
curl "localhost:8001/products?search=wireless"

# 3. Add to cart (cart_id can be any string — session/user ID in production)
curl -X POST localhost:8002/carts/my-cart/items \
  -H "Content-Type: application/json" \
  -d '{"product_id": 1, "quantity": 2}'

# 4. Place an order
curl -X POST localhost:8003/orders \
  -H "Content-Type: application/json" \
  -d '{"cart_id": "my-cart", "customer_email": "buyer@example.com"}'
```

### 4. Run Tests (No Docker Needed)

```bash
cd services/catalog
python -m venv venv && venv\Scripts\activate   # Windows
pip install -r requirements.txt -r requirements-dev.txt
pytest -v
```

Tests run against an **in-memory SQLite database** — no Postgres, no Docker, no network. Each test gets a clean set of tables via an autouse fixture.

```
tests/test_products.py::test_health                              PASSED
tests/test_products.py::test_create_product                      PASSED
tests/test_products.py::test_create_product_duplicate_sku_409    PASSED
tests/test_products.py::test_get_product_by_id                   PASSED
tests/test_products.py::test_get_product_not_found               PASSED
tests/test_products.py::test_list_products_empty                 PASSED
tests/test_products.py::test_list_products_returns_all           PASSED
tests/test_products.py::test_search_by_name_case_insensitive     PASSED
tests/test_products.py::test_search_by_sku                       PASSED
tests/test_products.py::test_pagination_limit                    PASSED
tests/test_products.py::test_pagination_skip                     PASSED
tests/test_products.py::test_pagination_limit_out_of_range_422   PASSED

12 passed ✓
```

---

## API Reference

### Catalog Service (`:8001`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/products` | List all products. Supports `?search=`, `?skip=`, `?limit=` query params |
| `GET` | `/products/{id}` | Get a single product by ID |
| `POST` | `/products` | Create a new product (enforces unique SKU — returns `409` on duplicate) |

### Cart Service (`:8002`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/carts/{cart_id}` | Get cart contents |
| `POST` | `/carts/{cart_id}/items` | Add item to cart (validates product exists via catalog service) |
| `DELETE` | `/carts/{cart_id}/items/{product_id}` | Remove item from cart |
| `DELETE` | `/carts/{cart_id}` | Clear entire cart |

### Orders Service (`:8003`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/orders/{id}` | Get order details with line items |
| `POST` | `/orders` | Create order from cart (fetches cart, looks up real prices from catalog, creates Stripe PaymentIntent, returns `client_secret`) |
| `PATCH` | `/orders/{id}/status` | Update order status (called by payments webhook on success/failure) |

### Payments Service (`:8004`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/payment-intents` | Create a Stripe PaymentIntent for an order |
| `POST` | `/webhooks/stripe` | Stripe webhook receiver — idempotent event processing |

---

## Design Decisions

### Why Schema-Per-Service on One Postgres Instance?

Running 4 separate Postgres containers locally eats RAM and adds operational complexity for zero benefit during development. Instead, each service gets its own [PostgreSQL schema](https://www.postgresql.org/docs/current/ddl-schemas.html) (`catalog`, `orders`, `payments`) — logically isolated, same migration story, and trivially swapped to separate RDS instances in production by changing one environment variable.

### Why Redis for Carts Instead of Postgres?

Carts are ephemeral, high-frequency, and session-scoped. Redis gives sub-millisecond reads with built-in TTL expiry (24 hours by default) — no cron jobs to clean up abandoned carts. The cart service stores items as a JSON blob per cart key, which keeps the data model flat and avoids join overhead.

### Why Idempotent Webhook Processing?

Stripe [explicitly recommends](https://stripe.com/docs/webhooks#handle-duplicate-events) handling webhook retries. The `ProcessedWebhookEvent` table tracks every Stripe event ID we've handled. If Stripe retries a delivery (network hiccup, timeout), we return `200 already_processed` instead of double-processing the payment — preventing duplicate charges or status flips.

### Why Store Money as Integer Cents?

Floating-point arithmetic causes rounding errors with currency (`0.1 + 0.2 ≠ 0.3`). Storing amounts as integer cents (`2999` = `$29.99`) eliminates this class of bugs entirely. This matches Stripe's own API convention.

### Why SQLite for Tests?

Tests should be fast, deterministic, and require zero infrastructure. SQLAlchemy's abstraction lets us swap the database URL from `postgresql://...` to `sqlite:///:memory:` in the test fixture — same ORM code, same queries, but tests run in ~200ms with no Docker dependency.

---

## Stripe Setup

1. Create a free [Stripe account](https://dashboard.stripe.com/register) and grab your **test mode** secret key
2. Add it to `services/payments/.env`:
   ```
   STRIPE_SECRET_KEY=sk_test_your_key_here
   ```
3. For local webhook testing, install the [Stripe CLI](https://stripe.com/docs/stripe-cli) and run:
   ```bash
   stripe listen --forward-to localhost:8004/webhooks/stripe
   ```
   Copy the `whsec_...` value it prints into `STRIPE_WEBHOOK_SECRET` in the same `.env` file.

---

## Project Structure

```
scalecart/
├── docker-compose.yml              # Orchestrates all 6 containers
├── infra/
│   └── init-db.sql                 # Creates per-service Postgres schemas
├── services/
│   ├── catalog/                    # Product management
│   │   ├── app/
│   │   │   ├── main.py             # FastAPI routes (CRUD + search + pagination)
│   │   │   ├── models.py           # SQLAlchemy Product model
│   │   │   ├── schemas.py          # Pydantic request/response schemas
│   │   │   └── db.py               # Engine, session, Base
│   │   ├── tests/
│   │   │   ├── conftest.py         # SQLite in-memory fixture + TestClient
│   │   │   └── test_products.py    # 12 tests covering CRUD, search, pagination, edge cases
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   ├── cart/                       # Redis-backed cart with cross-service validation
│   │   ├── app/
│   │   │   ├── main.py             # Add/remove/clear + catalog product validation
│   │   │   └── schemas.py          # CartItem, CartOut
│   │   ├── tests/
│   │   │   ├── conftest.py         # fakeredis fixture + TestClient
│   │   │   └── test_cart.py        # 13 tests — add/remove/clear, quantity merge, error paths
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   ├── orders/                     # Order lifecycle management
│   │   ├── app/
│   │   │   ├── main.py             # Cart fetch → catalog price lookup → payment → order creation
│   │   │   ├── models.py           # Order + OrderItem + OrderStatus enum
│   │   │   ├── schemas.py          # OrderCreate, OrderOut, OrderStatusUpdate
│   │   │   └── db.py
│   │   ├── tests/
│   │   │   ├── conftest.py         # SQLite in-memory fixture + TestClient
│   │   │   └── test_orders.py      # 11 tests — full flow, error paths, status update
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   └── payments/                   # Stripe integration
│       ├── app/
│       │   ├── main.py             # PaymentIntent creation + idempotent webhook handler
│       │   ├── models.py           # PaymentIntentRecord + ProcessedWebhookEvent
│       │   ├── schemas.py          # PaymentIntentCreate, PaymentIntentOut
│       │   └── db.py
│       ├── tests/
│       │   ├── conftest.py         # SQLite in-memory fixture + TestClient
│       │   └── test_payments.py    # 10 tests — Stripe mocks, webhook idempotency, error paths
│       ├── Dockerfile
│       └── requirements.txt
└── .github/
    └── workflows/
        └── ci.yml                  # GitHub Actions: 4 parallel test jobs on every push/PR
```

---

## Development Progress

### ✅ Completed

- [x] **Microservice skeleton** — 4 FastAPI services, Docker Compose, health checks, hot-reload
- [x] **Catalog service** — full CRUD, case-insensitive search (name + SKU), cursor pagination
- [x] **Catalog test suite** — 12 pytest tests, in-memory SQLite, edge cases (409 duplicate SKU, 404 not found, 422 validation)
- [x] **Cart service** — Redis-backed add/remove/clear, quantity merging, cross-service product validation
- [x] **Orders service** — cart fetch, order creation with line items, status enum (`pending`/`paid`/`failed`/`fulfilled`/`cancelled`)
- [x] **Payments service** — Stripe PaymentIntent creation, webhook handling, idempotent event tracking
- [x] **Database isolation** — schema-per-service on shared Postgres, auto-created via init SQL
- [x] **Cart test suite** — 13 pytest tests using fakeredis (in-memory Redis) + respx (httpx mock), covering add/remove/clear, quantity merging, catalog validation (200/404/503), payload validation, and cart isolation
- [x] **Python 3.13 compatibility** — all dependencies pinned to versions with prebuilt wheels
- [x] **Orders → Payments wiring** — create PaymentIntent on order placement, return `client_secret`
- [x] **Webhook → Orders callback** — flip `order.status` to `paid` on `payment_intent.succeeded`
- [x] **Real price lookup** — replace placeholder unit price with catalog service call in order creation
- [x] **Orders test suite** — 11 pytest tests using respx to mock cart, catalog, and payments upstream calls
- [x] **Payments test suite** — 10 pytest tests using `unittest.mock` to mock Stripe SDK + respx for orders callback, covering PaymentIntent creation, webhook processing (succeeded/failed), idempotent duplicate detection, invalid signatures
- [x] **CI/CD pipeline** — GitHub Actions running all 46 tests across 4 services in parallel on every push/PR

### 🔧 In Progress

- [ ] **Auth** — JWT-based authentication middleware

### 📋 Planned

- [ ] **Async workflows** — SQS + Lambda for email confirmation, inventory updates, receipt generation
- [ ] **AWS deployment** — EC2 Auto Scaling + ALB, RDS, ElastiCache, ECS
- [ ] **Static assets** — S3 + CloudFront CDN for product images
- [ ] **Category model** — product categorization and filtered browsing

---

## License

MIT
