-- Runs once when the postgres container is first created.
-- Gives each microservice its own schema so they stay logically isolated
-- even though they share one Postgres instance (cheap for local/dev + early prod).

CREATE SCHEMA IF NOT EXISTS catalog;
CREATE SCHEMA IF NOT EXISTS orders;
CREATE SCHEMA IF NOT EXISTS payments;

-- cart intentionally has no schema here — it lives in Redis, not Postgres.
