"""Register (with rollback), login, refresh, logout, lookups."""
from tests.conftest import bearer

REG = {"full_name": "Njeri Wambui", "national_id": "31234567", "phone": "0712345678", "password": "Sup3rSecret", "ward_id": 1}


def test_register_creates_auth_user_farmer_and_first_plot(world):
    r = world.client.post("/auth/register", json=REG)
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["access_token"] and data["refresh_token"] and data["user"]["role"] == "farmer"
    farmer = next(f for f in world.repo.farmers.values() if f["national_id"] == "31234567")
    assert farmer["phone"] == "254712345678"  # normalised from 07...
    assert any(p["farmer_id"] == farmer["id"] for p in world.repo.plots.values())
    assert len(world.gateway.users) == 1


def test_register_rolls_back_auth_user_when_database_insert_fails(world):
    world.repo.fail_create_farmer = True
    r = world.client.post("/auth/register", json=REG)
    assert r.status_code == 500
    assert world.gateway.users == {}           # auth user compensated away
    assert len(world.gateway.deleted) == 1
    assert not any(f["national_id"] == "31234567" for f in world.repo.farmers.values())


def test_register_duplicate_national_id_or_phone_is_409_and_creates_nothing(world):
    for over in ({"national_id": "30000001"}, {"phone": "254711000002"}):
        r = world.client.post("/auth/register", json={**REG, **over})
        assert r.status_code == 409 and r.json()["error"]["code"] == "ALREADY_REGISTERED"
    assert world.gateway.users == {}


def test_register_validation(world):
    bad = [{"phone": "0612345678"}, {"phone": "25471234"}, {"national_id": "12ab"}, {"password": "short1"},
           {"password": "onlyletters"}, {"full_name": "A"}, {"ward_id": 0}, {"email": "nope"}, {"role": "admin"}]
    for over in bad:
        r = world.client.post("/auth/register", json={**REG, **over})
        assert r.status_code == 422, over
    assert world.client.post("/auth/register", json={**REG, "ward_id": 99}).status_code == 422
    assert world.gateway.users == {}


def test_login_by_phone_and_by_email_and_wrong_password(world):
    world.client.post("/auth/register", json={**REG, "email": "njeri@example.com"})
    world.repo.auth_emails["254712345678"] = "njeri@example.com"
    for ident in ("0712345678", "+254712345678", "254712345678", "Njeri@Example.com"):
        r = world.client.post("/auth/login", json={"identifier": ident, "password": "Sup3rSecret"})
        assert r.status_code == 200, ident
        assert r.json()["user"]["role"] == "farmer"
    bad_pw = world.client.post("/auth/login", json={"identifier": "0712345678", "password": "wrong"})
    unknown = world.client.post("/auth/login", json={"identifier": "0799999999", "password": "Sup3rSecret"})
    assert bad_pw.status_code == unknown.status_code == 401
    assert bad_pw.json()["error"]["message"] == unknown.json()["error"]["message"]  # no account enumeration


def test_refresh_rotates_and_old_refresh_token_is_dead(world):
    tokens = world.client.post("/auth/register", json=REG).json()
    r = world.client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 200 and r.json()["refresh_token"] != tokens["refresh_token"]
    reuse = world.client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert reuse.status_code == 401 and reuse.json()["error"]["code"] == "REFRESH_FAILED"


def test_logout_requires_valid_token_and_revokes_session(world):
    tokens = world.client.post("/auth/register", json=REG).json()
    assert world.client.post("/auth/logout").status_code == 401
    r = world.client.post("/auth/logout", headers=bearer(tokens["access_token"]))
    assert r.status_code == 204 and world.gateway.signed_out == [tokens["access_token"]]


def test_locations_are_public_and_produce_types_are_not(world):
    assert world.client.get("/locations").status_code == 200
    assert len(world.client.get("/locations").json()) == 3
    assert world.client.get("/produce-types").status_code == 401
    assert world.client.get("/produce-types", headers=world.h(world.farmer1["user_id"])).status_code == 200
