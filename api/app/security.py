"""JWT verification for Supabase access tokens.

We NEVER trust the client: the signature, exp, iss and aud are all verified here, with the
algorithm list pinned (so `alg: none` and HS/RS key-confusion attacks are rejected).
The user's ROLE is not read from the token at all — see deps.get_current_user.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import jwt
from jwt import PyJWKClient

from .config import Settings
from .errors import ServiceUnavailable, Unauthorized


@dataclass(frozen=True)
class TokenClaims:
    user_id: UUID
    email: str | None
    session_id: str | None


class TokenVerifier:
    def __init__(self, settings: Settings):
        self._aud = settings.jwt_audience
        self._iss = settings.issuer
        self._leeway = settings.jwt_leeway_seconds
        self._mode = settings.jwt_mode
        self._secret = settings.supabase_jwt_secret
        # PyJWKClient caches keys, so we only hit the JWKS endpoint on key rotation.
        self._jwks = PyJWKClient(settings.jwks_url, cache_keys=True, lifespan=600) if self._mode == "jwks" else None

    def verify(self, token: str) -> TokenClaims:
        try:
            if self._mode == "hs256":
                key: object = self._secret
                algorithms = ["HS256"]
            else:
                key = self._jwks.get_signing_key_from_jwt(token).key  # type: ignore[union-attr]
                algorithms = ["ES256", "RS256"]
            payload = jwt.decode(
                token,
                key,  # type: ignore[arg-type]
                algorithms=algorithms,
                audience=self._aud,
                issuer=self._iss,
                leeway=self._leeway,
                options={"require": ["exp", "iss", "aud", "sub"], "verify_signature": True,
                         "verify_exp": True, "verify_aud": True, "verify_iss": True},
            )
        except jwt.ExpiredSignatureError:
            raise Unauthorized("Access token has expired", code="TOKEN_EXPIRED") from None
        except jwt.PyJWKClientConnectionError:
            raise ServiceUnavailable("Could not fetch signing keys") from None
        except jwt.PyJWTError:
            # Bad signature, wrong aud/iss, missing claim, malformed, alg mismatch...
            # One generic message: do not tell an attacker which check failed.
            raise Unauthorized("Invalid access token", code="INVALID_TOKEN") from None

        # The anon key is also a Supabase-signed JWT; it has no `sub`, but be explicit.
        if payload.get("role") != "authenticated":
            raise Unauthorized("Invalid access token", code="INVALID_TOKEN")
        try:
            user_id = UUID(str(payload["sub"]))
        except ValueError:
            raise Unauthorized("Invalid access token", code="INVALID_TOKEN") from None
        return TokenClaims(user_id=user_id, email=payload.get("email"), session_id=payload.get("session_id"))
