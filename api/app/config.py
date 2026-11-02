"""Configuration — everything comes from environment variables (see .env.example)."""
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Supabase project ---------------------------------------------------
    supabase_url: str = Field(description="https://<ref>.supabase.co")
    supabase_anon_key: str = Field(description="Public anon key; used only to call GoTrue sign-in/refresh")
    supabase_service_role_key: str = Field(description="SERVER ONLY. Used to create/delete auth users")

    # --- JWT verification ---------------------------------------------------
    # Legacy projects sign tokens with a shared secret (HS256). Projects that use
    # asymmetric signing keys publish a JWKS document instead. If a secret is set we
    # verify HS256, otherwise we fetch the JWKS (ES256/RS256).
    supabase_jwt_secret: str | None = None
    jwt_audience: str = "authenticated"
    jwt_issuer: str | None = None  # defaults to <supabase_url>/auth/v1
    jwt_leeway_seconds: int = 5

    # --- Database (Supabase Postgres connection string; service-side only) ---
    database_url: str

    # --- Misc ---------------------------------------------------------------
    phone_login_email_domain: str = "phone.farmers.example"
    cors_origins: str = ""  # comma-separated; the mobile app does not need CORS
    db_pool_max: int = 10

    @property
    def issuer(self) -> str:
        return self.jwt_issuer or f"{self.supabase_url.rstrip('/')}/auth/v1"

    @property
    def jwks_url(self) -> str:
        return f"{self.issuer}/.well-known/jwks.json"

    @property
    def jwt_mode(self) -> str:
        return "hs256" if self.supabase_jwt_secret else "jwks"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
