"""
models.py
---------
SQLAlchemy ORM model(s) for the database.

Currently contains a single table: `participants`.
"""

import enum
from datetime import datetime, timedelta, timezone

from sqlalchemy import Column, Integer, String, DateTime, Enum, Index, ForeignKey, func, Text

IST = timezone(timedelta(hours=5, minutes=30))

from database import Base


class PaymentStatus(str, enum.Enum):
    """Allowed values for a participant's payment_status column."""
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class RegistrationStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    REGISTRATION_OPEN = "REGISTRATION_OPEN"
    REGISTRATION_CLOSED = "REGISTRATION_CLOSED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class Workshop(Base):
    __tablename__ = "workshops"

    id = Column(Integer, primary_key=True)
    workshop_name = Column(String, nullable=False)
    slug = Column(String, nullable=False, unique=True, index=True)
    workshop_date = Column(String, nullable=False)
    start_time = Column(String, nullable=False)
    end_time = Column(String, nullable=False)
    timezone = Column(String, nullable=False, default="Asia/Kolkata")
    price_paise = Column(Integer, nullable=False)
    max_seats = Column(Integer, nullable=False)
    registration_status = Column(Enum(RegistrationStatus), nullable=False, default=RegistrationStatus.REGISTRATION_OPEN)
    description = Column(Text, nullable=False, default="")
    mode = Column(String, nullable=False, default="Online Live Session")
    learning_points = Column(Text, nullable=False, default="[]")
    meeting_platform = Column(String, nullable=True)
    meeting_id = Column(String, nullable=True)
    meeting_url = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(IST), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(IST), onupdate=lambda: datetime.now(IST), nullable=False)
    updated_by = Column(String, nullable=True)


class WorkshopAudit(Base):
    __tablename__ = "workshop_audits"

    id = Column(Integer, primary_key=True)
    workshop_id = Column(Integer, ForeignKey("workshops.id"), nullable=False, index=True)
    changed_at = Column(DateTime(timezone=True), default=lambda: datetime.now(IST), nullable=False)
    changed_by = Column(String, nullable=False)
    old_values = Column(Text, nullable=False)
    new_values = Column(Text, nullable=False)


class BrandingSettings(Base):
    __tablename__ = "branding_settings"

    id = Column(Integer, primary_key=True)
    brand_name = Column(String(80), nullable=False)
    brand_mark = Column(String(5), nullable=False)
    brand_accent_color = Column(String(7), nullable=False)
    instructor_name = Column(String(120), nullable=False)
    instructor_title = Column(String(120), nullable=False)
    instructor_bio = Column(Text, nullable=False)
    instructor_email = Column(String(254), nullable=False)
    registration_roles = Column(Text, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(IST), onupdate=lambda: datetime.now(IST), nullable=False)
    updated_by = Column(String, nullable=True)


class Participant(Base):
    """
    Represents one workshop registration.

    NOTE:
    - `amount` is always set by the backend (see main.py), never by the client.
    - `payment_status` starts as PENDING and can only become SUCCESS after a
      verified Razorpay signature (see payment.py).
    """

    __tablename__ = "participants"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String, nullable=False)
    email = Column(String, nullable=False, index=True)
    whatsapp = Column(String, nullable=False)
    role = Column(String, nullable=False)
    experience = Column(String, nullable=True)
    workshop = Column(String, nullable=False)
    amount_paise = Column(Integer, nullable=False)
    payment_status = Column(Enum(PaymentStatus), nullable=False, default=PaymentStatus.PENDING)
    razorpay_order_id = Column(String, nullable=True, index=True)
    razorpay_payment_id = Column(String, nullable=True)
    payment_token_hash = Column(String, nullable=True, unique=True, index=True)
    registered_at = Column(DateTime(timezone=True), default=lambda: datetime.now(IST), nullable=False)
    payment_timestamp = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_participant_email_workshop", "email", "workshop"),
        Index("ix_participant_email_workshop_unique", func.lower(email), "workshop", unique=True),
        Index("ix_participant_whatsapp_workshop_unique", func.lower(whatsapp), "workshop", unique=True),
    )

    @property
    def amount(self) -> int:
        return self.amount_paise // 100


class PaymentAttempt(Base):
    __tablename__ = "payment_attempts"

    id = Column(Integer, primary_key=True, index=True)
    participant_id = Column(Integer, ForeignKey("participants.id"), nullable=False, index=True)
    razorpay_order_id = Column(String, nullable=False, unique=True, index=True)
    razorpay_payment_id = Column(String, nullable=True, unique=True, index=True)
    amount_paise = Column(Integer, nullable=False)
    status = Column(Enum(PaymentStatus), nullable=False, default=PaymentStatus.PENDING)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(IST), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)


class SeatCounter(Base):
    __tablename__ = "seat_counters"

    workshop = Column(String, primary_key=True)
    max_seats = Column(Integer, nullable=False)
    allocated_seats = Column(Integer, nullable=False, default=0)


class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    id = Column(Integer, primary_key=True)
    provider_event_id = Column(String, nullable=False, unique=True, index=True)
    event_type = Column(String, nullable=False)
    received_at = Column(DateTime(timezone=True), default=lambda: datetime.now(IST), nullable=False)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String, nullable=False, default="PROCESSING")
    participant_id = Column(Integer, ForeignKey("participants.id"), nullable=True)
    payment_attempt_id = Column(Integer, ForeignKey("payment_attempts.id"), nullable=True)


class NotificationStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SENT = "SENT"
    FAILED = "FAILED"


class NotificationOutbox(Base):
    __tablename__ = "notification_outbox"

    id = Column(Integer, primary_key=True)
    idempotency_key = Column(String, nullable=False, unique=True, index=True)
    participant_id = Column(Integer, ForeignKey("participants.id"), nullable=False, index=True)
    event_type = Column(String, nullable=False)
    payload = Column(Text, nullable=False)
    status = Column(Enum(NotificationStatus), nullable=False, default=NotificationStatus.PENDING)
    attempt_count = Column(Integer, nullable=False, default=0)
    next_retry_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    last_error = Column(String, nullable=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)
