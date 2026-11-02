"""Thin client for Supabase Auth (GoTrue). The API is the only component that holds the
service-role key; the mobile app never sees it."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

import httpx

from .config import Settings
from .errors import Conflict, ServiceUnavailable, Unauthorized, Unprocessable

log = logging.getLogger("api.auth")


@dataclass
class Session:
    access_token: str
    refresh_token: str
    expires_in: int
    expires_at: int
    user_id: UUID


class AuthGateway(Protocol):
    def create_user(self, *, email: str, password: str, full_name: str) -> UUID: ...
    def delete_user(self, user_id: UUID) -> None: ...
    def sign_in(self, *, email: str, password: str) -> Session: ...
    def refresh(self, refresh_token: str) -> Session: ...
    def sign_out(self, access_token: str) -> None: ...


class SupabaseAuthGateway:
    def __init__(self, settings: Settings, client: httpx.Client | None = None):
        self._base = f"{settings.supabase_url.rstrip('/')}/auth/v1"
        self._anon = settings.supabase_anon_key
        self._service = settings.supabase_service_role_key
        self._http = client or httpx.Client(timeout=10.0)

    # -- helpers
    def _admin_headers(self) -> dict[str, str]:
        headers = {"apikey": self._service}
        if self._service.startswith("eyJ"):  # legacy JWT-style keys only; new sb_secret_ keys are not JWTs
            headers["Authorization"] = f"Bearer {self._service}"
        return headers

    def _request(self, method: str, path: str, **kw: Any) -> httpx.Response:
        try:
            return self._http.request(method, f"{self._base}{path}", **kw)
        except httpx.HTTPError as exc:
            log.warning("auth upstream error: %s", exc.__class__.__name__)
            raise ServiceUnavailable("Authentication service is unavailable") from None

    @staticmethod
    def _session(data: dict[str, Any]) -> Session:
        return Session(access_token=data["access_token"], refresh_token=data["refresh_token"],
                       expires_in=int(data["expires_in"]), expires_at=int(data.get("expires_at", 0)),
                       user_id=UUID(data["user"]["id"]))

    # -- admin
    def create_user(self, *, email: str, password: str, full_name: str) -> UUID:
        r = self._request("POST", "/admin/users", headers=self._admin_headers(), json={
            "email": email, "password": password, "email_confirm": True,
            "user_metadata": {"full_name": full_name},
        })
        if r.status_code in (200, 201):
            return UUID(r.json()["id"])
        if r.status_code in (409, 422) and "exist" in r.text.lower():
            raise Conflict("An account with these details already exists", code="ACCOUNT_EXISTS")
        if r.status_code in (400, 422):
            raise Unprocessable("The authentication service rejected the credentials (is the password strong enough?)")
        log.error("create_user failed status=%s", r.status_code)
        raise ServiceUnavailable("Could not create the account")

    def delete_user(self, user_id: UUID) -> None:
        r = self._request("DELETE", f"/admin/users/{user_id}", headers=self._admin_headers())
        if r.status_code not in (200, 204):
            raise RuntimeError(f"delete_user failed with status {r.status_code}")

    # -- end-user flows
    def sign_in(self, *, email: str, password: str) -> Session:
        r = self._request("POST", "/token", params={"grant_type": "password"},
                          headers={"apikey": self._anon}, json={"email": email, "password": password})
        if r.status_code == 200:
            return self._session(r.json())
        if r.status_code in (400, 401, 422):
            raise Unauthorized("Invalid credentials", code="INVALID_CREDENTIALS")
        raise ServiceUnavailable("Authentication service is unavailable")

    def refresh(self, refresh_token: str) -> Session:
        r = self._request("POST", "/token", params={"grant_type": "refresh_token"},
                          headers={"apikey": self._anon}, json={"refresh_token": refresh_token})
        if r.status_code == 200:
            return self._session(r.json())
        if r.status_code in (400, 401, 403, 422):
            raise Unauthorized("Session expired, please sign in again", code="REFRESH_FAILED")
        raise ServiceUnavailable("Authentication service is unavailable")

    def sign_out(self, access_token: str) -> None:
        # scope=local revokes this session's refresh tokens only (other devices stay signed in)
        r = self._request("POST", "/logout", params={"scope": "local"},
                          headers={"apikey": self._anon, "Authorization": f"Bearer {access_token}"})
        if r.status_code not in (200, 204, 401):
            raise ServiceUnavailable("Authentication service is unavailable")
