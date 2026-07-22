import pytest
import fakeredis
from fastapi.testclient import TestClient

import app.main as cart_main


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    """Swap the real Redis client for an in-memory fake.

    Every test gets a fresh, empty Redis — no server needed, no state
    leaking between tests.
    """
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(cart_main, "r", fake)
    yield fake
    fake.flushall()


@pytest.fixture
def client():
    """FastAPI TestClient wired to the cart app."""
    return TestClient(cart_main.app)
