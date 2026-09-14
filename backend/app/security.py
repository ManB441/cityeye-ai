"""Security configuration and HTTP response hardening."""

from __future__ import annotations

from dataclasses import dataclass
import os
from urllib.parse import urlparse


VALID_ENVIRONMENTS = {"development", "demo", "production"}


def _csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


@dataclass(frozen=True)
class SecuritySettings:
    environment: str
    cors_origins: tuple[str, ...]
    trusted_hosts: tuple[str, ...]
    docs_enabled: bool

    @classmethod
    def from_environment(cls) -> "SecuritySettings":
        environment = os.getenv("CITYEYE_ENVIRONMENT", "development").lower()
        if environment not in VALID_ENVIRONMENTS:
            raise ValueError(
                f"CITYEYE_ENVIRONMENT must be one of {sorted(VALID_ENVIRONMENTS)}"
            )

        default_origins = (
            "http://127.0.0.1:5173,http://localhost:5173"
            if environment == "development"
            else ""
        )
        default_hosts = "*" if environment != "production" else ""
        cors_origins = _csv(os.getenv("CITYEYE_CORS_ORIGINS", default_origins))
        trusted_hosts = _csv(os.getenv("CITYEYE_TRUSTED_HOSTS", default_hosts))

        if "*" in cors_origins:
            raise ValueError("CITYEYE_CORS_ORIGINS cannot contain a wildcard")
        for origin in cors_origins:
            parsed = urlparse(origin)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError(f"Invalid CORS origin: {origin}")
            if parsed.path not in {"", "/"} or parsed.params or parsed.query or parsed.fragment:
                raise ValueError(f"CORS origin must not include a path: {origin}")

        if environment == "production":
            if not trusted_hosts or "*" in trusted_hosts:
                raise ValueError(
                    "Production requires explicit CITYEYE_TRUSTED_HOSTS without wildcards"
                )
            if any("change-me" in host.lower() for host in trusted_hosts):
                raise ValueError("Replace CHANGE-ME in CITYEYE_TRUSTED_HOSTS")
            insecure_origins = [
                origin for origin in cors_origins if not origin.startswith("https://")
            ]
            if insecure_origins:
                raise ValueError("Production CORS origins must use HTTPS")
            if any("change-me" in origin.lower() for origin in cors_origins):
                raise ValueError("Replace CHANGE-ME in CITYEYE_CORS_ORIGINS")

        return cls(
            environment=environment,
            cors_origins=cors_origins,
            trusted_hosts=trusted_hosts,
            docs_enabled=environment != "production",
        )


SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
}
