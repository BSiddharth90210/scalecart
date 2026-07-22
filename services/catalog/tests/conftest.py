import os

# Must happen BEFORE `app.db` (and therefore `app.main`) is imported anywhere,
# since the engine is built once at import time from this env var.
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db import Base, engine


@pytest.fixture(autouse=True)
def _fresh_schema():
    """Give every single test a clean set of tables — no leftover data
    from the previous test leaking in."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
