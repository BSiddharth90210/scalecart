import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import StaticPool

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://scalecart:scalecart_dev_pw@localhost:5432/scalecart",
)

connect_args = {}
pool_kwargs = {}
if DATABASE_URL.startswith("postgres"):
    connect_args["options"] = "-csearch_path=orders"
    pool_kwargs["pool_pre_ping"] = True
elif DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False
    pool_kwargs["poolclass"] = StaticPool

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    **pool_kwargs,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
