import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import StaticPool

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://scalecart:scalecart_dev_pw@localhost:5432/scalecart",
)

if DATABASE_URL.startswith("sqlite"):
    # Used for the test suite only — an in-memory DB, no Postgres required.
    # StaticPool keeps the same connection alive so the in-memory DB persists
    # across the multiple sessions FastAPI opens during a test.
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
else:
    # All catalog tables live in the "catalog" Postgres schema.
    engine = create_engine(
        DATABASE_URL,
        connect_args={"options": "-csearch_path=catalog"},
        pool_pre_ping=True,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
