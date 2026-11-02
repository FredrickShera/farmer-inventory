"""Runs the REAL PostgresRepository + SQL against a seeded database.

Skipped unless TEST_DATABASE_URL is set. Prepare a database with:
    db/tests/run_local.sh            (creates `farmer_test` with stub auth schema, migrations, seed.sql)
then:  TEST_DATABASE_URL=postgresql://postgres@/farmer_test pytest tests/test_db_integration.py
Only the Supabase Auth HTTP service is faked; everything else is real SQL (triggers, constraints, scoping).
"""
from __future__ import annotations

import os
from uuid import UUID, uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.repository import ItemSold, PostgresRepository
from tests.conftest import SECRET, SUPABASE_URL, bearer, make_token
from tests.fakes import FakeGateway
from app.errors import Conflict, Unprocessable

DSN = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DSN, reason="set TEST_DATABASE_URL to run DB integration tests")

# Seeded ids (db/seed.sql)
WANJIRU_USER, PETER_USER = UUID("f0000000-0000-4000-8000-000000000001"), UUID("f0000000-0000-4000-8000-000000000002")
OFFICER_NAIROBI = UUID("b0000000-0000-4000-8000-000000000001")
OFFICER_RIFT = UUID("b0000000-0000-4000-8000-000000000002")
ADMIN = UUID("a0000000-0000-4000-8000-000000000001")
PETER_ITEM = "e0000000-0000-4000-8000-000000000006"
SOLD_ITEM = UUID("e0000000-0000-4000-8000-000000000005")
WANJIRU_PLOT = "d0000000-0000-4000-8000-000000000001"


class DbGateway(FakeGateway):
    """Fake GoTrue that really inserts into auth.users so FK constraints are exercised."""

    def create_user(self, *, email, password, full_name):
        uid = uuid4()
        with psycopg.connect(DSN, autocommit=True) as c:
            c.execute("insert into auth.users (id, email) values (%s, %s)", (uid, email))
        self.users[email] = (uid, password)
        return uid

    def delete_user(self, user_id):
        with psycopg.connect(DSN, autocommit=True) as c:
            c.execute("delete from auth.users where id = %s", (user_id,))
        super().delete_user(user_id)


@pytest.fixture(scope="module")
def stack():
    repo = PostgresRepository(DSN, max_size=4)
    repo.open()
    settings = Settings(supabase_url=SUPABASE_URL, supabase_anon_key="a", supabase_service_role_key="s",
                        supabase_jwt_secret=SECRET, database_url=DSN)
    gateway = DbGateway(lambda uid: make_token(uid))
    client = TestClient(create_app(settings, repo=repo, gateway=gateway), raise_server_exceptions=False)
    yield client, repo, gateway
    # clean up everything the tests registered
    with psycopg.connect(DSN, autocommit=True) as c:
        c.execute("delete from public.inventory_items where farmer_id in (select id from public.farmers where national_id like '39%')")
        c.execute("delete from public.plots where farmer_id in (select id from public.farmers where national_id like '39%')")
        c.execute("delete from public.farmers where national_id like '39%'")
        c.execute("delete from public.user_roles where user_id in (select id from auth.users where email like '%@test.invalid')")
        c.execute("delete from auth.users where email like '%@test.invalid'")
    repo.close()


def h(uid: UUID) -> dict[str, str]:
    return bearer(make_token(uid))


def test_seeded_farmer_profile_and_plots(stack):
    client, *_ = stack
    r = client.get("/farmers/me", headers=h(WANJIRU_USER))
    assert r.status_code == 200
    data = r.json()
    assert data["full_name"] == "Wanjiru Mwangi" and data["ward"] == "Kitisuru" and data["county"] == "Nairobi"
    assert {p["name"] for p in data["plots"]} == {"Home plot", "Kangundo plot"}


def test_farmer_scope_in_sql(stack):
    client, *_ = stack
    r = client.get("/inventory?page_size=100", headers=h(WANJIRU_USER)).json()
    assert r["total"] == 3 and all(i["farmer_name"] == "Wanjiru Mwangi" for i in r["items"])
    assert client.get(f"/inventory/{PETER_ITEM}", headers=h(WANJIRU_USER)).status_code == 404


def test_officer_scope_matches_rls(stack):
    client, *_ = stack
    nairobi = client.get("/farmers?page_size=100", headers=h(OFFICER_NAIROBI)).json()
    assert {f["full_name"] for f in nairobi["items"]} == {"Wanjiru Mwangi", "Samuel Mutua"}   # same as rls_test.sql
    assert client.get("/inventory?page_size=100", headers=h(OFFICER_NAIROBI)).json()["total"] == 5
    rift = client.get("/inventory?page_size=100", headers=h(OFFICER_RIFT)).json()
    assert rift["total"] == 6
    assert client.get(f"/farmers/{'c0000000-0000-4000-8000-000000000002'}", headers=h(OFFICER_NAIROBI)).status_code == 404


def test_admin_filters_in_sql(stack):
    client, *_ = stack
    assert client.get("/inventory?page_size=100", headers=h(ADMIN)).json()["total"] == 12
    assert client.get("/inventory?status=sold", headers=h(ADMIN)).json()["total"] == 1
    assert client.get("/inventory?grade=C&page_size=100", headers=h(ADMIN)).json()["total"] == 2
    tomatoes = client.get("/produce-types", headers=h(ADMIN)).json()
    tid = next(p["id"] for p in tomatoes if p["name"] == "Tomatoes")
    assert client.get(f"/inventory?produce_type_id={tid}", headers=h(ADMIN)).json()["total"] == 2
    assert client.get("/farmers?page=1&page_size=2", headers=h(ADMIN)).json()["has_more"] is True


def test_register_login_create_and_idempotent_post_with_real_sql(stack):
    client, repo, gateway = stack
    reg = {"full_name": "Test Farmer", "national_id": "39000001", "phone": "254722000001",
           "email": "t1@test.invalid", "password": "Sup3rSecret", "ward_id": 1}
    ward = client.get("/locations").json()[0]["ward_id"]
    reg["ward_id"] = ward
    r = client.post("/auth/register", json=reg)
    assert r.status_code == 201, r.text
    token = r.json()["access_token"]
    me = client.get("/farmers/me", headers=bearer(token)).json()
    plot = me["plots"][0]["id"]
    body = {"plot_id": plot, "produce_type_id": 1, "quantity": "12.50", "unit": "crate", "grade": "A",
            "expected_harvest_date": "2026-12-01", "asking_price_minor": 12345, "client_request_id": str(uuid4())}
    a = client.post("/inventory", json=body, headers=bearer(token))
    b = client.post("/inventory", json=body, headers=bearer(token))
    assert (a.status_code, b.status_code) == (201, 200) and a.json()["id"] == b.json()["id"]
    assert client.get("/inventory", headers=bearer(token)).json()["total"] == 1
    # duplicate registration is refused before touching auth
    assert client.post("/auth/register", json={**reg, "email": "t2@test.invalid"}).status_code == 409


def test_register_rolls_back_for_real_when_db_rejects(stack):
    client, repo, gateway = stack
    before = len(gateway.users)
    # A ward that passes the API check but a plot name that violates a DB CHECK (length 81) -> DB rejects.
    # We call the repository the same way the route does, then compensate as the route does.
    uid = gateway.create_user(email="rb@test.invalid", password="x", full_name="x")
    with pytest.raises(Unprocessable):
        repo.create_farmer(uid, {"full_name": "R B", "national_id": "39000002", "phone": "254722000002", "email": None, "ward_id": 1}, "p" * 81)
    gateway.delete_user(uid)
    with psycopg.connect(DSN) as c:
        assert c.execute("select count(*) from public.farmers where national_id = '39000002'").fetchone()[0] == 0
        assert c.execute("select count(*) from public.user_roles where user_id = %s", (uid,)).fetchone()[0] == 0  # tx rolled back
    assert len(gateway.users) == before


def test_database_trigger_blocks_sold_item_even_if_api_check_were_bypassed(stack):
    _, repo, _ = stack
    with pytest.raises(ItemSold):
        repo.update_inventory(SOLD_ITEM, {"quantity": 1})
    with pytest.raises(ItemSold):
        repo.soft_delete_inventory(SOLD_ITEM)


def test_database_rejects_negative_quantity_even_if_api_check_were_bypassed(stack):
    _, repo, _ = stack
    with pytest.raises(Unprocessable):
        repo.update_inventory(UUID("e0000000-0000-4000-8000-000000000001"), {"quantity": -1})


def test_database_rejects_other_farmers_plot_even_if_api_check_were_bypassed(stack):
    _, repo, _ = stack
    peter_plot = UUID("d0000000-0000-4000-8000-000000000003")
    with pytest.raises(Unprocessable):
        repo.update_inventory(UUID("e0000000-0000-4000-8000-000000000001"), {"plot_id": peter_plot})


def test_unique_violation_maps_to_409(stack):
    client, *_ = stack
    r = client.patch("/farmers/me", json={"phone": "254711000002"}, headers=h(WANJIRU_USER))  # Peter's number
    assert r.status_code == 409 and r.json()["error"]["details"][0]["field"] == "phone"
    assert client.get("/farmers/me", headers=h(WANJIRU_USER)).json()["phone"] == "254711000001"


def test_login_by_phone_uses_real_lookup(stack):
    client, repo, gateway = stack
    with psycopg.connect(DSN, autocommit=True) as c:
        c.execute("update auth.users set email = 'wanjiru@coop.example' where id = %s", (WANJIRU_USER,))
    assert repo.auth_email_for_phone("254711000001") == "wanjiru@coop.example"
    assert repo.auth_email_for_phone("254700000000") is None
