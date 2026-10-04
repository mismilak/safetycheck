import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="sc-test-")
os.environ.update(SC_DATA_DIR=_tmp, SC_DETECTOR="demo", SC_ADMIN_PASSWORD="Admin1234", SC_MODELS_DIR=_tmp)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

H = {"x-sc": "1"}


class Client(TestClient):
    def login(self, user="admin", pw="Admin1234"):
        r = self.post("/api/auth/login", json={"username": user, "password": pw}, headers=H)
        return r


@pytest.fixture(scope="session")
def client():
    with Client(app) as c:
        yield c


def make_client(client_cls=Client):
    return client_cls(app)
