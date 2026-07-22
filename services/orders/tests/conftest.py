import os

# Point at in-memory SQLite BEFORE anything imports app.db (which reads
# DATABASE_URL at import time to build the engine).
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db import Base, engine


@pytest.fixture(autouse=True)
def _fresh_schema():
    """Give every test a clean set of tables — no leftover rows."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
