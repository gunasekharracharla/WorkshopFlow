"""
schemas.py
----------
Pydantic schemas used for:
- Validating incoming request data (e.g. ParticipantCreate)
- Shaping outgoing response data (e.g. ParticipantResponse)

Keeping these separate from the SQLAlchemy models (models.py) means the
API's public "shape" never accidentally leaks internal database details,
and lets us validate input strictly before it ever touches the database.
"""

import re
from datetime import date, datetime, time
from typing import List, Optional

import phonenumbers
from phonenumbers import NumberParseException, PhoneNumberFormat, PhoneNumberType
from pydantic import BaseModel, EmailStr, field_validator, ConfigDict

from config import settings
from models import PaymentStatus, RegistrationStatus

# Retained for compatibility with callers that need the default workshop name.
WORKSHOP_NAME = settings.workshop_name


# ---------------------------------------------------------------------------
# WhatsApp number helpers (international, stored as E.164 e.g. +919876543210)
# ---------------------------------------------------------------------------

# Number types accepted for WhatsApp (toll-free, premium-rate, pager... are rejected).
_ALLOWED_PHONE_TYPES = {
    PhoneNumberType.MOBILE,
    PhoneNumberType.FIXED_LINE,
    PhoneNumberType.FIXED_LINE_OR_MOBILE,
    PhoneNumberType.VOIP,
}


def _is_artificial_number(national: str) -> bool:
    """True for obvious fake full numbers: 1111111111, 1234567890, 9876543210 ..."""
    if len(national) < 7:
        return False
    if len(set(national)) == 1:
        return True
    steps = {(int(b) - int(a)) % 10 for a, b in zip(national, national[1:])}
    return steps == {1} or steps == {9}  # full ascending / descending run


def normalize_whatsapp(value: str) -> str:
    """
    Validate a WhatsApp number and return it in E.164 format.

    - A leading "+" (or "00") means the number carries its own country code.
    - Anything else is treated as an Indian number, exactly as the original
      form did, so 9876543210 / 09876543210 / 91-9876543210 still work.
    - Indian numbers keep the original rule (10-digit mobile starting 6-9);
      every other country is validated with Google's libphonenumber data.
    """
    cleaned = re.sub(r"[\s\-().]", "", value or "")
    if cleaned.startswith("00"):
        cleaned = "+" + cleaned[2:]
    try:
        parsed = phonenumbers.parse(cleaned, None if cleaned.startswith("+") else "IN")
    except NumberParseException:
        raise ValueError(_INVALID_WHATSAPP)

    national = phonenumbers.national_significant_number(parsed)
    if parsed.country_code == 91:
        valid = re.fullmatch(r"[6-9]\d{9}", national) is not None
    else:
        valid = (
            phonenumbers.is_valid_number(parsed)
            and phonenumbers.number_type(parsed) in _ALLOWED_PHONE_TYPES
        )
    if not valid or _is_artificial_number(national):
        raise ValueError(_INVALID_WHATSAPP)
    return phonenumbers.format_number(parsed, PhoneNumberFormat.E164)


def whatsapp_lookup_values(e164: str) -> List[str]:
    """Values to match when checking for an existing registration.

    Older registrations stored Indian numbers as the bare 10 digits, so an
    Indian E.164 number must also match that legacy format.
    """
    values = [e164]
    if e164.startswith("+91") and len(e164) == 13:
        values.append(e164[3:])
    return values


_INVALID_WHATSAPP = (
    "Invalid WhatsApp number. Provide a valid mobile number for the selected "
    "country, e.g. +919876543210"
)


# ---------------------------------------------------------------------------
# Registration schemas
# ---------------------------------------------------------------------------

class ParticipantCreate(BaseModel):
    """What the client must send to POST /register."""

    name: str
    email: EmailStr
    whatsapp: str
    role: str
    # Optional: the form may omit "Years of Experience" entirely.
    experience: Optional[str] = None
    workshop: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2:
            raise ValueError("Name must be at least 2 characters long")
        if len(v) > 100:
            raise ValueError("Name is too long")
        return v

    @field_validator("whatsapp")
    @classmethod
    def validate_whatsapp(cls, v: str) -> str:
        """
        Accepts an international number (e.g. +1 415 555 2671, +44 7911 123456)
        or, for backwards compatibility, an Indian number without a country
        code (9876543210, 09876543210, 91-9876543210), and normalizes it to
        E.164 (+919876543210).
        """
        return normalize_whatsapp(v)

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) > 60:
            raise ValueError("Role must contain 1 to 60 characters")
        return v

    @field_validator("experience")
    @classmethod
    def validate_experience(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        if v == "":
            return None

        if not v.isdigit():
            raise ValueError(
                "Experience must be a whole number of years, e.g. '5', "
                "or omitted entirely"
            )
        years = int(v)
        if years < 0 or years > 60:
            raise ValueError("Experience must be between 0 and 60 years")
        return v

    @field_validator("workshop")
    @classmethod
    def validate_workshop(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) > 160:
            raise ValueError("Workshop name must contain 1 to 160 characters")
        return v


class ParticipantResponse(BaseModel):
    """What the API returns to describe one participant."""

    id: int
    name: str
    email: EmailStr
    whatsapp: str
    role: str
    experience: Optional[str] = None
    workshop: str
    amount: int
    payment_status: PaymentStatus
    razorpay_order_id: Optional[str] = None
    razorpay_payment_id: Optional[str] = None
    registered_at: datetime

    # Allows creating this schema directly from a SQLAlchemy model instance.
    model_config = ConfigDict(from_attributes=True)


class PublicParticipantResponse(BaseModel):
    id: int
    workshop: str
    amount: int
    payment_token: Optional[str] = None
    payment_status: PaymentStatus
    registered_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WorkshopResponse(BaseModel):
    name: str
    date: str
    start_time: str
    end_time: str
    time: str
    mode: str
    price: int
    currency: str
    max_seats: int
    confirmed_seats: int
    registration_open: bool
    registration_message: Optional[str] = None
    slug: str
    timezone: str
    registration_status: RegistrationStatus
    description: str
    mode: str
    learning_points: List[str]
    available_seats: int


class WorkshopAdminUpdate(BaseModel):
    workshop_name: str
    slug: str
    workshop_date: str
    start_time: str
    end_time: str
    timezone: str
    price_paise: int
    max_seats: int
    registration_status: RegistrationStatus
    description: str = ""
    mode: str = "Online Live Session"
    learning_points: List[str] = []
    meeting_platform: Optional[str] = None
    meeting_id: Optional[str] = None
    meeting_url: Optional[str] = None

    @field_validator("workshop_name", "slug", "timezone", "mode")
    @classmethod
    def required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("This field is required")
        return value

    @field_validator("slug")
    @classmethod
    def valid_slug(cls, value: str) -> str:
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", value):
            raise ValueError("Slug must contain lowercase letters, numbers, and hyphens")
        return value

    @field_validator("workshop_date")
    @classmethod
    def valid_date(cls, value: str) -> str:
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("Workshop date must use YYYY-MM-DD") from exc
        return value

    @field_validator("start_time", "end_time")
    @classmethod
    def valid_time(cls, value: str) -> str:
        try:
            time.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("Workshop time must use HH:MM or HH:MM:SS") from exc
        return value

    @field_validator("price_paise")
    @classmethod
    def valid_price(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Price must be greater than zero")
        return value

    @field_validator("max_seats")
    @classmethod
    def valid_seats(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Maximum seats must be greater than zero")
        return value

    @field_validator("meeting_url")
    @classmethod
    def valid_meeting_url(cls, value: Optional[str]) -> Optional[str]:
        if value and not re.match(r"^https://", value.strip(), re.IGNORECASE):
            raise ValueError("Meeting URL must use HTTPS")
        return value.strip() if value else None


class WorkshopAdminResponse(WorkshopResponse):
    meeting_platform: Optional[str] = None
    meeting_id: Optional[str] = None
    meeting_url: Optional[str] = None
    updated_at: datetime
    updated_by: Optional[str] = None


class WorkshopAuditResponse(BaseModel):
    id: int
    changed_at: datetime
    changed_by: str
    old_values: dict
    new_values: dict


class WorkshopStatsResponse(BaseModel):
    workshop_name: str
    registration_status: RegistrationStatus
    max_seats: int
    registered_count: int
    paid_count: int
    available_seats: int
    pending_payments: int
    failed_payments: int


class BrandingSettingsUpdate(BaseModel):
    brand_name: str
    brand_mark: str
    brand_accent_color: str
    instructor_name: str
    instructor_title: str
    instructor_bio: str
    instructor_email: EmailStr
    registration_roles: List[str]

    @field_validator(
        "brand_name",
        "brand_mark",
        "brand_accent_color",
        "instructor_name",
        "instructor_title",
        "instructor_bio",
        mode="before",
    )
    @classmethod
    def strip_brand_text(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value

    @field_validator("brand_name")
    @classmethod
    def valid_brand_name(cls, value: str) -> str:
        if not value or len(value) > 80:
            raise ValueError("Brand name must contain 1 to 80 characters")
        return value

    @field_validator("brand_mark")
    @classmethod
    def valid_brand_mark(cls, value: str) -> str:
        if not value or len(value) > 5:
            raise ValueError("Brand mark must contain 1 to 5 characters")
        return value

    @field_validator("brand_accent_color")
    @classmethod
    def valid_brand_color(cls, value: str) -> str:
        if not re.fullmatch(r"#[0-9A-Fa-f]{6}", value):
            raise ValueError("Accent color must use six-digit hex notation, e.g. #6b5bdd")
        return value

    @field_validator("instructor_name", "instructor_title")
    @classmethod
    def valid_instructor_text(cls, value: str) -> str:
        if not value or len(value) > 120:
            raise ValueError("Instructor name and title must contain 1 to 120 characters")
        return value

    @field_validator("instructor_bio")
    @classmethod
    def valid_instructor_bio(cls, value: str) -> str:
        if not value or len(value) > 1200:
            raise ValueError("Instructor bio must contain 1 to 1200 characters")
        return value

    @field_validator("registration_roles")
    @classmethod
    def valid_registration_roles(cls, values: List[str]) -> List[str]:
        roles = [role.strip() for role in values if role.strip()]
        if not roles or len(roles) > 20 or any(len(role) > 60 for role in roles):
            raise ValueError("Provide 1 to 20 attendee roles, each at most 60 characters")
        if len(set(roles)) != len(roles):
            raise ValueError("Attendee roles must be unique")
        return roles


class BrandingSettingsResponse(BrandingSettingsUpdate):
    updated_at: Optional[datetime] = None
    updated_by: Optional[str] = None


# ---------------------------------------------------------------------------
# Payment schemas
# ---------------------------------------------------------------------------

class PaymentCreateRequest(BaseModel):
    """What the client sends to POST /payment/create."""
    participant_id: int
    payment_token: str


class PaymentCreateResponse(BaseModel):
    """
    What the API returns after creating a Razorpay order.

    The frontend (Member 1) will use these fields to open Razorpay Checkout.
    Note: key_id is PUBLIC and safe to expose. The key SECRET never leaves
    the backend.
    """
    razorpay_order_id: str
    amount: int
    currency: str
    key_id: str
    participant_id: int


class PaymentVerifyRequest(BaseModel):
    """
    What the client sends to POST /payment/verify.

    These three fields are exactly what Razorpay Checkout returns to the
    frontend after a successful payment attempt.
    """
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class PaymentVerifyResponse(BaseModel):
    """What the API returns after attempting to verify a payment."""
    success: bool
    message: str
    participant: ParticipantResponse
