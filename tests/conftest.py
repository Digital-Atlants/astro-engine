import os

import pytest
from fastapi.testclient import TestClient

os.environ["SERVICE_API_KEY"] = "test-key"

from astro_engine.main import app  # noqa: E402

AUTH = {"Authorization": "Bearer test-key"}


@pytest.fixture(scope="session")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(scope="session")
def auth_headers() -> dict:
    return AUTH
