import logging

from fastapi import APIRouter, Depends, Response, status

from ..auth_gateway import AuthGateway, Session
from ..config import Settings
from ..deps import get_gateway, get_raw_token, get_claims, get_repo, get_settings_dep
from ..errors import Conflict, Unauthorized, Unprocessable
from ..repository import Repository
from ..schemas import (LoginRequest, RefreshRequest, RegisterRequest, SessionUser, TokenResponse,
                       normalise_phone, PHONE_RE)

router = APIRouter(prefix="/auth", tags=["auth"])
log = logging.getLogger("api.auth")


def _token_response(session: Session, repo: Repository) -> TokenResponse:
    role = repo.get_role(session.user_id)
    user = None
    if role:
        farmer = repo.get_farmer_by_user(session.user_id) if role == "farmer" else None
        user = SessionUser(id=session.user_id, role=role, farmer_id=farmer["id"] if farmer else None)
    return TokenResponse(access_token=session.access_token, refresh_token=session.refresh_token,
                         expires_in=session.expires_in, expires_at=session.expires_at, user=user)


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED,
             summary="Create the Supabase Auth user and the farmer profile (both or neither)")
def register(body: RegisterRequest, repo: Repository = Depends(get_repo), gateway: AuthGateway = Depends(get_gateway),
             settings: Settings = Depends(get_settings_dep)):
    if not repo.ward_exists(body.ward_id):
        raise Unprocessable("Invalid ward", details=[{"field": "ward_id", "message": "unknown ward"}])
    if clashes := repo.find_conflicts(body.national_id, body.phone):
        raise Conflict("A farmer with these details is already registered", code="ALREADY_REGISTERED",
                       details=[{"field": f, "message": "already registered"} for f in clashes])

    auth_email = body.email or f"{body.phone}@{settings.phone_login_email_domain}"
    # Step 1: auth user. Step 2: database rows. If step 2 fails we compensate by deleting the auth user,
    # so neither half is left behind ("roll back both").
    user_id = gateway.create_user(email=auth_email, password=body.password, full_name=body.full_name)
    try:
        repo.create_farmer(user_id, {"full_name": body.full_name, "national_id": body.national_id, "phone": body.phone,
                                     "email": body.email, "ward_id": body.ward_id}, body.plot_name)
    except Exception:
        try:
            gateway.delete_user(user_id)
        except Exception:  # pragma: no cover - needs manual clean-up, make it loud
            log.critical("ORPHANED AUTH USER %s: farmer insert failed and compensation delete failed", user_id)
        raise
    session = gateway.sign_in(email=auth_email, password=body.password)
    return _token_response(session, repo)


@router.post("/login", response_model=TokenResponse, summary="Exchange phone/email + password for a session")
def login(body: LoginRequest, repo: Repository = Depends(get_repo), gateway: AuthGateway = Depends(get_gateway)):
    ident = body.identifier.strip()
    if "@" in ident:
        email: str | None = ident.lower()
    else:
        phone = normalise_phone(ident)
        email = repo.auth_email_for_phone(phone) if PHONE_RE.fullmatch(phone) else None
    if email is None:
        # Same answer as a wrong password: do not reveal whether the phone is registered.
        raise Unauthorized("Invalid credentials", code="INVALID_CREDENTIALS")
    return _token_response(gateway.sign_in(email=email, password=body.password), repo)


@router.post("/refresh", response_model=TokenResponse, summary="Rotate the refresh token and get a new access token")
def refresh(body: RefreshRequest, repo: Repository = Depends(get_repo), gateway: AuthGateway = Depends(get_gateway)):
    return _token_response(gateway.refresh(body.refresh_token), repo)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Revoke the current session")
def logout(token: str = Depends(get_raw_token), _claims=Depends(get_claims), gateway: AuthGateway = Depends(get_gateway)):
    gateway.sign_out(token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
