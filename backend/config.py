import os
import re
from dataclasses import dataclass
from dotenv import load_dotenv
from urllib.parse import urlparse

load_dotenv()


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name, str(default)).strip()
    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _hex_color(name: str, default: str) -> str:
    value = _env(name, default)
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", value):
        raise RuntimeError(f"{name} must be a six-digit hex color such as #6b5bdd")
    return value


def _policy_url(name: str) -> str:
    value = _env(name)
    if not value:
        return ""
    parsed = urlparse(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
    ):
        raise RuntimeError(f"{name} must be an absolute HTTP or HTTPS URL without credentials or query parameters")
    return value


def _bool_env(name: str, default: bool = False) -> bool:
    value = _env(name, str(default)).lower()
    if value not in {"true", "false"}:
        raise RuntimeError(f"{name} must be true or false")
    return value == "true"


def _registration_roles() -> tuple[str, ...]:
    roles = tuple(
        role.strip()
        for role in _env(
            "REGISTRATION_ROLES",
            "Full-Stack Developer,Frontend Developer,Backend Developer,Web Designer,Student/Fresher,Other",
        ).split(",")
        if role.strip()
    )
    if not roles or any(len(role) > 60 for role in roles) or len(set(roles)) != len(roles):
        raise RuntimeError("REGISTRATION_ROLES must contain unique role names of at most 60 characters")
    return roles


@dataclass(frozen=True)
class Settings:
    app_env: str = _env("APP_ENV", "development").lower()
    brand_name: str = _env("BRAND_NAME", "WorkshopFlow")
    brand_mark: str = _env("BRAND_MARK", "WF")
    brand_accent_color: str = _hex_color("BRAND_ACCENT_COLOR", "#6b5bdd")
    instructor_name: str = _env("INSTRUCTOR_NAME", "Your workshop instructor")
    instructor_title: str = _env("INSTRUCTOR_TITLE", "Workshop facilitator")
    instructor_bio: str = _env(
        "INSTRUCTOR_BIO",
        "I help professionals turn expert knowledge into structured learning experiences, premium registrations, and repeatable workshop growth.",
    )
    instructor_email: str = _env("INSTRUCTOR_EMAIL", "your.email@example.com")
    privacy_policy_url: str = _policy_url("PRIVACY_POLICY_URL")
    registration_terms_url: str = _policy_url("REGISTRATION_TERMS_URL")
    data_backups_verified: bool = _bool_env("DATA_BACKUPS_VERIFIED")
    production_monitoring_configured: bool = _bool_env("PRODUCTION_MONITORING_CONFIGURED")
    payment_operations_reviewed: bool = _bool_env("PAYMENT_OPERATIONS_REVIEWED")
    admin_rate_limiting_configured: bool = _bool_env("ADMIN_RATE_LIMITING_CONFIGURED")
    registration_roles: tuple[str, ...] = _registration_roles()
    workshop_name: str = _env("WORKSHOP_NAME", "WorkshopFlow Launch Workshop")
    workshop_date: str = _env("WORKSHOP_DATE", "To be announced")
    workshop_start_time: str = _env("WORKSHOP_START_TIME", "4:00 PM")
    workshop_end_time: str = _env("WORKSHOP_END_TIME", "5:30 PM")
    workshop_price: int = _int_env("WORKSHOP_PRICE", 399)
    early_bird_price: int = _int_env("EARLY_BIRD_PRICE", 399)
    max_seats: int = _int_env("MAX_SEATS", 100)
    meeting_url: str = _env("MEETING_URL")
    meeting_password: str = _env("MEETING_PASSWORD")
    database_url: str = _env("DATABASE_URL", "sqlite:///./workshop.db")
    frontend_origins: tuple[str, ...] = tuple(
        origin.strip()
        for origin in os.getenv("FRONTEND_URLS", "http://localhost:8000,http://127.0.0.1:8000,http://localhost:5500,http://127.0.0.1:5500").split(",")
        if origin.strip()
    )
    admin_username: str = _env("ADMIN_USERNAME")
    admin_password: str = _env("ADMIN_PASSWORD")


settings = Settings()


def validate_runtime_settings() -> None:
    if settings.app_env != "production":
        return
    required = {
        "RAZORPAY_KEY_ID": _env("RAZORPAY_KEY_ID"),
        "RAZORPAY_KEY_SECRET": _env("RAZORPAY_KEY_SECRET"),
        "RAZORPAY_WEBHOOK_SECRET": _env("RAZORPAY_WEBHOOK_SECRET"),
        "ADMIN_USERNAME": settings.admin_username,
        "ADMIN_PASSWORD": settings.admin_password,
        "DATABASE_URL": settings.database_url,
        "PRIVACY_POLICY_URL": settings.privacy_policy_url,
        "REGISTRATION_TERMS_URL": settings.registration_terms_url,
        "FRONTEND_URLS": ",".join(settings.frontend_origins),
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise RuntimeError(f"Production configuration missing required values: {', '.join(missing)}")
    if settings.admin_username.lower() in {"admin", "administrator"} or len(settings.admin_password) < 16:
        raise RuntimeError("Production admin credentials require a non-default username and a password of at least 16 characters")
    if any(not origin.lower().startswith("https://") or "*" in origin for origin in settings.frontend_origins):
        raise RuntimeError("Production FRONTEND_URLS must contain only explicit HTTPS origins")
    if any(
        not value.startswith("https://")
        for value in (settings.privacy_policy_url, settings.registration_terms_url)
    ):
        raise RuntimeError("Production privacy and registration policy URLs must use HTTPS")


def workshop_payload(confirmed_seats: int) -> dict:
    return {
        "name": settings.workshop_name,
        "date": settings.workshop_date,
        "start_time": settings.workshop_start_time,
        "end_time": settings.workshop_end_time,
        "time": f"{settings.workshop_start_time} – {settings.workshop_end_time}",
        "mode": "Online Live Session",
        "price": settings.workshop_price,
        "currency": "INR",
        "max_seats": settings.max_seats,
        "confirmed_seats": confirmed_seats,
        "registration_open": confirmed_seats < settings.max_seats,
    }