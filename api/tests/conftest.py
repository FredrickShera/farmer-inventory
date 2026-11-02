from __future__ import annotations

import time
from dataclasses import dataclass
from uuid import UUID, uuid4

import jwt
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.fakes import FakeGateway, FakeRepo

SECRET = "test-secret-test-secret-test-secret-32b"
SUPABASE_URL = "https://testproject.supabase.co"
ISS = f"{SUPABASE_URL}/auth/v1"


def make_token(sub: UUID | str, *, secret: str = SECRET, exp_in: int = 3600, iss: str = ISS, aud: str = "authenticated",
               role: str = "authenticated", extra: dict | None = None, algorithm: str = "HS256") -> str:
    now = int(time.time())
    payload = {"sub": str(sub), "aud": aud, "iss": iss, "role": role, "iat": now, "exp": now + exp_in,
               "email": "someone@example.com", **(extra or {})}
    return jwt.encode(payload, secret, algorithm=algorithm)


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@dataclass
class World:
    client: TestClient
    repo: FakeRepo
    gateway: FakeGateway
    # users
    farmer1: dict
    farmer2: dict
    farmer3: dict
    officer: UUID          # covers ward 1 only
    admin: UUID
    norole: UUID           # valid Supabase user, no row in user_roles
    # items
    item1: dict            # farmer1, available
    item2: dict            # farmer2, available (ward 2)
    sold1: dict            # farmer1, sold

    def h(self, user_id: UUID, **kw) -> dict[str, str]:
        return bearer(make_token(user_id, **kw))


@pytest.fixture
def world() -> World:
    settings = Settings(supabase_url=SUPABASE_URL, supabase_anon_key="anon", supabase_service_role_key="service",
                        supabase_jwt_secret=SECRET, database_url="postgresql://unused")
    repo = FakeRepo()
    f1 = repo.add_farmer(uuid4(), "Wanjiru Mwangi", 1, national_id="30000001", phone="254711000001")
    f2 = repo.add_farmer(uuid4(), "Peter Kiptoo", 2, national_id="30000002", phone="254711000002")
    f3 = repo.add_farmer(uuid4(), "Grace Akinyi", 3, national_id="30000003", phone="254711000003")
    officer, admin, norole = uuid4(), uuid4(), uuid4()
    repo.roles.update({officer: "officer", admin: "admin"})
    repo.officer_wards[officer] = [1]
    plot = lambda f: next(p for p in repo.plots.values() if p["farmer_id"] == f["id"])
    item1 = repo.add_item(f1["id"], plot(f1)["id"])
    item2 = repo.add_item(f2["id"], plot(f2)["id"])
    sold1 = repo.add_item(f1["id"], plot(f1)["id"], status="sold")
    gateway = FakeGateway(lambda uid: make_token(uid))
    app = create_app(settings, repo=repo, gateway=gateway)
    return World(TestClient(app, raise_server_exceptions=False), repo, gateway, f1, f2, f3, officer, admin, norole,
                 item1, item2, sold1)
