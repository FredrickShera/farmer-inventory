"""Reusable auth dependencies.

  get_claims        -> verifies the bearer token (401 if missing/invalid/expired)
  get_current_user  -> + loads the role FROM THE DATABASE (never from the token/body/user_metadata)
  require_roles(..) -> 403 when the (valid) caller's role is not allowed
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable
from uuid import UUID

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .auth_gateway import AuthGateway
from .config import Settings
from .errors import Forbidden, Unauthorized
from .repository import Repository
from .security import TokenClaims, TokenVerifier

# auto_error=False: FastAPI's default would answer 403 for a missing header; we want 401.
_bearer = HTTPBearer(auto_error=False, description="Supabase access token")


def get_repo(request: Request) -> Repository:
    return request.app.state.repo


def get_gateway(request: Request) -> AuthGateway:
    return request.app.state.gateway


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_raw_token(creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> str:
    if creds is None or creds.scheme.lower() != "bearer" or not creds.credentials:
        raise Unauthorized("Missing bearer token", code="MISSING_TOKEN")
    return creds.credentials


def get_claims(request: Request, token: str = Depends(get_raw_token)) -> TokenClaims:
    verifier: TokenVerifier = request.app.state.verifier
    return verifier.verify(token)


@dataclass
class CurrentUser:
    user_id: UUID
    email: str | None
    role: str
    farmer: dict[str, Any] | None = None
    ward_ids: list[int] = field(default_factory=list)

    @property
    def farmer_id(self) -> UUID | None:
        return self.farmer["id"] if self.farmer else None


def get_current_user(claims: TokenClaims = Depends(get_claims), repo: Repository = Depends(get_repo)) -> CurrentUser:
    role = repo.get_role(claims.user_id)  # trusted source: public.user_roles
    if role is None:
        # valid token, but this account has no application role
        raise Forbidden("Your account has no access to this service", code="NO_ROLE")
    user = CurrentUser(user_id=claims.user_id, email=claims.email, role=role)
    if role == "farmer":
        farmer = repo.get_farmer_by_user(claims.user_id)
        if farmer is None:
            raise Forbidden("Farmer profile not found", code="PROFILE_MISSING")
        if farmer["status"] != "active":
            raise Forbidden("This account is not active", code="ACCOUNT_INACTIVE")
        user.farmer = farmer
    elif role == "officer":
        user.ward_ids = repo.officer_ward_ids(claims.user_id)
    return user


def require_roles(*allowed: str) -> Callable[..., CurrentUser]:
    def dependency(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in allowed:
            raise Forbidden("You do not have permission to perform this action")
        return user

    return dependency
