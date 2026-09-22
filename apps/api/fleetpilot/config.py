import json
from functools import lru_cache
from typing import Literal
from urllib.parse import urlparse

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="../../.env", extra="ignore", hide_input_in_errors=True
    )
    environment: Literal["development", "test", "production"] = "development"
    reporting_synthetic_trips_json: str = "{}"
    database_url: str
    migration_database_url: str | None = None
    web_origin: str = "http://localhost:3000"
    session_lifetime_seconds: int = 28800
    login_limit: int = 10
    evidence_storage_root: str | None = None
    storage_backend: Literal["local", "s3"] = "local"
    s3_endpoint: str | None = None
    s3_bucket: str | None = None
    s3_region: str = "us-east-1"
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    s3_allow_insecure_loopback: bool = False
    rate_limit_backend: Literal["memory", "postgres"] = "memory"
    mutation_limit: int = 120
    upload_limit: int = 30
    evidence_access_limit: int = 120

    @field_validator("database_url")
    @classmethod
    def postgres_only(cls, value: str) -> str:
        if not value.startswith("postgresql+asyncpg://"):
            raise ValueError("PostgreSQL asyncpg URL required")
        return value

    @model_validator(mode="after")
    def secure_production(self):
        if self.environment == "production" and self.reporting_synthetic_trips_json != "{}":
            raise ValueError("Local synthetic reporting configuration is prohibited in production")
        try:
            manifest = json.loads(self.reporting_synthetic_trips_json)
            if not isinstance(manifest, dict) or len(manifest) > 100:
                raise ValueError("Invalid synthetic manifest")
            from uuid import UUID

            for organization, identifiers in manifest.items():
                UUID(organization)
                if not isinstance(identifiers, list) or len(identifiers) > 5000:
                    raise ValueError("Invalid synthetic trip list")
                for identifier in identifiers:
                    UUID(identifier)
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError("Invalid synthetic reporting configuration") from exc
        parsed = urlparse(self.web_origin)
        if not parsed.netloc or parsed.path not in ("", "/"):
            raise ValueError("WEB_ORIGIN must be an origin without a path")
        if self.environment == "production" and parsed.scheme != "https":
            raise ValueError("Production requires HTTPS")
        if self.session_lifetime_seconds < 60:
            raise ValueError("Session lifetime must be at least 60 seconds")
        if (
            parsed.scheme not in {"http", "https"}
            or parsed.username
            or parsed.query
            or parsed.fragment
            or "*" in self.web_origin
        ):
            raise ValueError("WEB_ORIGIN must be a single HTTP(S) origin")
        if (
            min(
                self.login_limit, self.mutation_limit, self.upload_limit, self.evidence_access_limit
            )
            < 1
        ):
            raise ValueError("Rate limits must be positive")
        if self.storage_backend == "s3":
            if not self.s3_bucket or not self.s3_region:
                raise ValueError("S3 bucket and region are required")
            if bool(self.s3_access_key) != bool(self.s3_secret_key):
                raise ValueError("Supply both S3 credentials or use the SDK credential chain")
            if self.s3_endpoint:
                endpoint = urlparse(self.s3_endpoint)
                local_test = self.s3_allow_insecure_loopback and endpoint.hostname in {
                    "localhost",
                    "127.0.0.1",
                }
                if endpoint.scheme != "https" and not (local_test and endpoint.scheme == "http"):
                    raise ValueError("S3 requires HTTPS (explicit loopback test exception only)")
                if (
                    not endpoint.hostname
                    or endpoint.username
                    or endpoint.query
                    or endpoint.fragment
                    or endpoint.path not in ("", "/")
                ):
                    raise ValueError("Invalid S3 endpoint")
        return self

    def validate_runtime(self) -> None:
        """Startup gate; opaque database sessions require no invented signing secret."""
        if self.environment == "production":
            if self.storage_backend != "s3" or self.rate_limit_backend != "postgres":
                raise RuntimeError(
                    "Production requires S3 storage and shared PostgreSQL rate limiting"
                )
            password = urlparse(self.database_url).password
            if (
                not password
                or len(password) < 16
                or password.lower().startswith(("replace", "changeme"))
            ):
                raise RuntimeError("Production database credentials must be explicitly provisioned")

    @property
    def cookie_secure(self) -> bool:
        return self.environment == "production" or self.web_origin.startswith("https://")


@lru_cache
def get_settings() -> Settings:
    return Settings()
