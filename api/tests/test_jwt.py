"""401 vs 403: every way a token can be bad must be a 401; a good token without permission must be a 403."""
import base64
import json
from uuid import uuid4

import jwt
import pytest

from tests.conftest import ISS, SECRET, bearer, make_token

URL = "/farmers/me"


def test_missing_token_is_401(world):
    r = world.client.get(URL)
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "MISSING_TOKEN"
    assert r.headers["www-authenticate"] == "Bearer"


def test_garbage_token_is_401(world):
    assert world.client.get(URL, headers=bearer("not.a.jwt")).status_code == 401


def test_expired_token_is_401(world):
    r = world.client.get(URL, headers=bearer(make_token(world.farmer1["user_id"], exp_in=-120)))
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "TOKEN_EXPIRED"


def test_tampered_payload_is_401(world):
    """Swap the subject to another farmer's id but keep the original signature."""
    header, payload, signature = make_token(world.farmer1["user_id"]).split(".")
    claims = json.loads(base64.urlsafe_b64decode(payload + "=="))
    claims["sub"] = str(world.admin)
    forged = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    r = world.client.get("/farmers", headers=bearer(f"{header}.{forged}.{signature}"))
    assert r.status_code == 401


def test_wrong_signing_secret_is_401(world):
    token = make_token(world.farmer1["user_id"], secret="x" * 40)
    assert world.client.get(URL, headers=bearer(token)).status_code == 401


def test_alg_none_is_401(world):
    token = jwt.encode({"sub": str(world.admin), "aud": "authenticated", "iss": ISS, "role": "authenticated",
                        "exp": 9999999999}, key=None, algorithm="none")
    assert world.client.get("/farmers", headers=bearer(token)).status_code == 401


def test_other_hmac_algorithm_is_401(world):
    """Algorithm list is pinned to HS256: an HS512 token signed with the right secret is refused."""
    assert world.client.get(URL, headers=bearer(make_token(world.farmer1["user_id"], algorithm="HS512"))).status_code == 401


@pytest.mark.parametrize("kw", [{"aud": "other"}, {"iss": "https://evil.example/auth/v1"}, {"role": "anon"}])
def test_wrong_audience_issuer_or_role_is_401(world, kw):
    assert world.client.get(URL, headers=bearer(make_token(world.farmer1["user_id"], **kw))).status_code == 401


def test_token_missing_required_claim_is_401(world):
    token = jwt.encode({"sub": str(uuid4()), "role": "authenticated"}, SECRET, algorithm="HS256")  # no exp/aud/iss
    assert world.client.get(URL, headers=bearer(token)).status_code == 401


def test_valid_token_without_role_is_403_not_401(world):
    r = world.client.get(URL, headers=world.h(world.norole))
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "NO_ROLE"


def test_role_comes_from_database_not_from_token_metadata(world):
    """A farmer whose token CLAIMS to be admin (user_metadata / app_metadata / role-ish claims) is still a farmer."""
    claims = {"user_metadata": {"role": "admin"}, "app_metadata": {"role": "admin"}, "user_role": "admin"}
    r = world.client.get("/farmers", headers=world.h(world.farmer1["user_id"], extra=claims))
    assert r.status_code == 403
    assert world.client.get(URL, headers=world.h(world.farmer1["user_id"], extra=claims)).status_code == 200


def test_error_envelope_is_consistent(world):
    for resp in (world.client.get(URL), world.client.get("/nope"), world.client.get("/farmers", headers=world.h(world.farmer1["user_id"]))):
        body = resp.json()
        assert set(body) == {"error"} and {"code", "message", "request_id"} <= set(body["error"])
