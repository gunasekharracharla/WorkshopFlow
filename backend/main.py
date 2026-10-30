"""Full-stack web development workshop application."""

import csv
import io
import json
import hashlib
import logging
import os
import re
import secrets
import threading
import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from typing import List

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, Security, status
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, text
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session

import models
import schemas
from config import settings, validate_runtime_settings, workshop_payload
from database import engine, get_db, run_additive_migrations, SessionLocal
from payment import (
    RAZORPAY_KEY_ID,
    RAZORPAY_KEY_SECRET,
    RAZORPAY_WEBHOOK_SECRET,
    AUTOMATION_WEBHOOK_URL,
    create_razorpay_order,
    send_payment_success_to_n8n,
    fetch_razorpay_order,
    fetch_razorpay_payment,
    verify_razorpay_signature,
    verify_razorpay_webhook_signature,
)

validate_runtime_settings()
if settings.app_env != "production":
    models.Base.metadata.create_all(bind=engine)
    run_additive_migrations()


def _ensure_workshop() -> models.Workshop:
    with SessionLocal() as db:
        workshop = db.query(models.Workshop).filter(models.Workshop.id == 1).first()
        if workshop and workshop.workshop_name == "MNRATHI AI Power Hour":
            old_name = workshop.workshop_name
            db.query(models.Participant).filter(
                models.Participant.workshop == old_name
            ).update(
                {models.Participant.workshop: settings.workshop_name},
                synchronize_session=False,
            )
            counter = db.get(models.SeatCounter, old_name)
            if counter:
                counter.workshop = settings.workshop_name
            workshop.workshop_name = settings.workshop_name
            workshop.slug = "full-stack-web-development"
            workshop.description = "A polished white-label workshop experience built to help trainers sell seats and manage registrations smoothly."
            db.commit()
            db.refresh(workshop)
        if not workshop:
            workshop = models.Workshop(
                workshop_name=settings.workshop_name,
                slug="full-stack-web-development",
                workshop_date=settings.workshop_date,
                start_time=settings.workshop_start_time,
                end_time=settings.workshop_end_time,
                timezone="Asia/Kolkata",
                price_paise=settings.workshop_price * 100,
                max_seats=settings.max_seats,
                registration_status=models.RegistrationStatus.REGISTRATION_OPEN,
                description="A polished white-label workshop experience built to help trainers sell seats and manage registrations smoothly.",
                mode="Online Live Session",
                learning_points=json.dumps([]),
                meeting_url=settings.meeting_url or None,
            )
            db.add(workshop)
            db.commit()
            db.refresh(workshop)
        return workshop


_ensure_workshop()


def get_workshop(db: Session) -> models.Workshop:
    workshop = db.query(models.Workshop).filter(models.Workshop.id == 1).first()
    if workshop:
        return workshop
    workshop = models.Workshop(
        workshop_name=settings.workshop_name,
        slug="full-stack-web-development",
        workshop_date=settings.workshop_date,
        start_time=settings.workshop_start_time,
        end_time=settings.workshop_end_time,
        timezone="Asia/Kolkata",
        price_paise=settings.workshop_price * 100,
        max_seats=settings.max_seats,
        registration_status=models.RegistrationStatus.REGISTRATION_OPEN,
        description="A polished white-label workshop experience built to help trainers sell seats and manage registrations smoothly.",
        mode="Online Live Session",
        learning_points=json.dumps([]),
        meeting_url=settings.meeting_url or None,
    )
    db.add(workshop)
    db.flush()
    return workshop


def _ensure_seat_counter() -> None:
    with SessionLocal() as db:
        workshop = db.query(models.Workshop).filter(models.Workshop.id == 1).one()
        if not db.get(models.SeatCounter, workshop.workshop_name):
            allocated = int(db.query(models.Participant).filter(
                models.Participant.workshop == workshop.workshop_name,
                models.Participant.payment_status == models.PaymentStatus.SUCCESS,
            ).count())
            db.add(models.SeatCounter(workshop=workshop.workshop_name, max_seats=workshop.max_seats, allocated_seats=allocated))
            try:
                db.commit()
            except SQLAlchemyError:
                db.rollback()


_ensure_seat_counter()

logger = logging.getLogger("mnrathi")

app = FastAPI(
    title="WorkshopFlow API",
    description="Branded workshop registration and server-verified Razorpay payments.",
    version="2.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.frontend_origins),
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "X-Razorpay-Signature"],
)

_notification_stop = threading.Event()
_notification_thread = None


def _notification_worker() -> None:
    while not _notification_stop.wait(5):
        try:
            process_pending_notifications()
        except Exception:  # pragma: no cover - worker must remain alive
            logger.exception("Notification worker failed")


@app.on_event("startup")
def start_notification_worker():
    global _notification_thread
    _notification_stop.clear()
    if _notification_thread is None or not _notification_thread.is_alive():
        _notification_thread = threading.Thread(target=_notification_worker, name="notification-outbox", daemon=True)
        _notification_thread.start()


@app.on_event("shutdown")
def stop_notification_worker():
    _notification_stop.set()

security = HTTPBasic(auto_error=False)
FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
ADMIN_DIR = os.path.abspath(os.path.join(FRONTEND_DIR, "admin"))
FRONTEND_INDEX = os.path.join(FRONTEND_DIR, "index.html")
PRODUCT_INDEX = os.path.join(FRONTEND_DIR, "product.html")
ADMIN_INDEX = os.path.join(ADMIN_DIR, "index.html")
HAS_FRONTEND = os.path.isdir(FRONTEND_DIR) and os.path.isfile(FRONTEND_INDEX)
HAS_PRODUCT_FRONTEND = os.path.isfile(PRODUCT_INDEX)
HAS_ADMIN_FRONTEND = os.path.isdir(ADMIN_DIR) and os.path.isfile(ADMIN_INDEX)


def require_admin(credentials: HTTPBasicCredentials | None = Security(security)):
    if not settings.admin_username or not settings.admin_password:
        raise HTTPException(status_code=503, detail="Admin access is not configured")
    if not credentials or not (
        secrets.compare_digest(credentials.username, settings.admin_username)
        and secrets.compare_digest(credentials.password, settings.admin_password)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin authentication required",
        )
    return credentials.username


def confirmed_seat_count(db: Session) -> int:
    return int(
        db.query(func.count(models.Participant.id))
        .filter(models.Participant.payment_status == models.PaymentStatus.SUCCESS)
        .scalar()
        or 0
    )


def branding_settings_payload(db: Session) -> dict:
    branding = db.get(models.BrandingSettings, 1)
    if branding:
        return {
            "brand_name": branding.brand_name,
            "brand_mark": branding.brand_mark,
            "brand_accent_color": branding.brand_accent_color,
            "instructor_name": branding.instructor_name,
            "instructor_title": branding.instructor_title,
            "instructor_bio": branding.instructor_bio,
            "instructor_email": branding.instructor_email,
            "registration_roles": json.loads(branding.registration_roles),
            "privacy_policy_url": settings.privacy_policy_url,
            "registration_terms_url": settings.registration_terms_url,
            "updated_at": branding.updated_at,
            "updated_by": branding.updated_by,
        }
    return {
        "brand_name": settings.brand_name,
        "brand_mark": settings.brand_mark,
        "brand_accent_color": settings.brand_accent_color,
        "instructor_name": settings.instructor_name,
        "instructor_title": settings.instructor_title,
        "instructor_bio": settings.instructor_bio,
        "instructor_email": settings.instructor_email,
        "registration_roles": list(settings.registration_roles),
        "privacy_policy_url": settings.privacy_policy_url,
        "registration_terms_url": settings.registration_terms_url,
        "updated_at": None,
        "updated_by": None,
    }


def payment_payload(db: Session, participant: models.Participant) -> dict:
    workshop = db.query(models.Workshop).filter(models.Workshop.workshop_name == participant.workshop).first()
    payload = {
        "participant_id": participant.id,
        "name": participant.name,
        "email": participant.email,
        "whatsapp": participant.whatsapp,
        "role": participant.role,
        "experience": participant.experience,
        "workshop": participant.workshop,
        "payment_id": participant.razorpay_payment_id,
        "order_id": participant.razorpay_order_id,
        "payment_status": participant.payment_status.value,
        "amount": participant.amount,
    }
    if workshop:
        payload.update({
            "meeting_platform": workshop.meeting_platform,
            "meeting_id": workshop.meeting_id,
            "meeting_url": workshop.meeting_url,
            "workshop_date": workshop.workshop_date,
            "start_time": workshop.start_time,
            "end_time": workshop.end_time,
            "timezone": workshop.timezone,
        })
    return payload


def _production_registration_ready(db: Session) -> bool:
    if settings.app_env != "production":
        return True
    return bool(product_readiness("system", db)["go_live_ready"])


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_payment_token() -> str:
    return secrets.token_urlsafe(32)


def enqueue_payment_notification(db: Session, participant: models.Participant) -> None:
    payload = payment_payload(db, participant)
    idempotency_key = f"workshop_registration_paid:{participant.id}"
    payload.update({
        "event_type": "payment.success",
        "event_version": 1,
        "idempotency_key": idempotency_key,
    })
    db.add(models.NotificationOutbox(
        idempotency_key=idempotency_key,
        participant_id=participant.id,
        event_type="payment.success",
        payload=json.dumps(payload),
        status=models.NotificationStatus.PENDING,
    ))


def allocate_seat(db: Session, participant: models.Participant) -> None:
    if db.bind.dialect.name == "sqlite":
        db.rollback()
        db.connection().exec_driver_sql("BEGIN IMMEDIATE")
    counter = db.query(models.SeatCounter).filter(models.SeatCounter.workshop == participant.workshop).with_for_update().one_or_none()
    if counter is None:
        workshop = db.query(models.Workshop).filter(models.Workshop.workshop_name == participant.workshop).first()
        counter = models.SeatCounter(workshop=participant.workshop, max_seats=workshop.max_seats if workshop else settings.max_seats, allocated_seats=0)
        db.add(counter)
        db.flush()
    if counter.allocated_seats >= counter.max_seats:
        raise HTTPException(status_code=409, detail="Registration is closed because all seats are filled")
    counter.allocated_seats += 1


def validate_provider_payment(db: Session, participant: models.Participant, attempt: models.PaymentAttempt, payment_id: str) -> None:
    try:
        provider_order = fetch_razorpay_order(attempt.razorpay_order_id)
        provider_payment = fetch_razorpay_payment(payment_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail="Payment provider validation failed") from exc
    if provider_payment.get("id") != payment_id or provider_payment.get("order_id") != attempt.razorpay_order_id:
        raise HTTPException(status_code=400, detail="Payment does not belong to this order")
    if provider_payment.get("status") not in {"captured", "authorized"}:
        raise HTTPException(status_code=400, detail="Payment has not been captured or authorized")
    if provider_payment.get("amount") != participant.amount_paise or provider_order.get("amount") != participant.amount_paise:
        raise HTTPException(status_code=400, detail="Payment amount mismatch")
    if provider_payment.get("currency") != "INR" or provider_order.get("currency") != "INR":
        raise HTTPException(status_code=400, detail="Payment currency mismatch")


def mark_payment_success(db: Session, participant: models.Participant, payment_id: str) -> models.Participant:
    db.rollback()
    participant = db.query(models.Participant).filter(models.Participant.id == participant.id).with_for_update().one()
    if participant.payment_status == models.PaymentStatus.SUCCESS:
        return participant
    if participant.payment_status == models.PaymentStatus.FAILED:
        raise HTTPException(status_code=409, detail="Payment status cannot be changed from FAILED to SUCCESS")
    attempt = db.query(models.PaymentAttempt).filter(
        models.PaymentAttempt.participant_id == participant.id,
        models.PaymentAttempt.razorpay_order_id == participant.razorpay_order_id,
    ).with_for_update().first()
    if not attempt or attempt.razorpay_order_id != participant.razorpay_order_id:
        raise HTTPException(status_code=409, detail="Payment attempt is no longer active")
    allocate_seat(db, participant)
    participant.payment_status = models.PaymentStatus.SUCCESS
    participant.razorpay_payment_id = payment_id
    participant.payment_timestamp = datetime.now(timezone(timedelta(hours=5, minutes=30)))
    attempt.razorpay_payment_id = payment_id
    attempt.status = models.PaymentStatus.SUCCESS
    attempt.completed_at = participant.payment_timestamp
    enqueue_payment_notification(db, participant)
    db.commit()
    db.refresh(participant)
    return participant


def process_pending_notifications(limit: int = 10, request_db: Session | None = None) -> int:
    processed = 0
    for _ in range(limit):
        owns_session = request_db is None
        db_context = SessionLocal() if owns_session else None
        db = db_context or request_db
        try:
            now = datetime.now(timezone.utc)
            item = db.query(models.NotificationOutbox).filter(
                models.NotificationOutbox.status.in_([models.NotificationStatus.PENDING, models.NotificationStatus.FAILED]),
                models.NotificationOutbox.next_retry_at <= now,
            ).order_by(models.NotificationOutbox.id).first()
            if not item:
                break
            claimed = db.query(models.NotificationOutbox).filter(
                models.NotificationOutbox.id == item.id,
                models.NotificationOutbox.status.in_([models.NotificationStatus.PENDING, models.NotificationStatus.FAILED]),
            ).update({
                "status": models.NotificationStatus.PROCESSING,
                "attempt_count": models.NotificationOutbox.attempt_count + 1,
            }, synchronize_session=False)
            db.commit()
            if not claimed:
                continue
            notification_id = item.id
            payload = json.loads(item.payload)
        finally:
            if db_context:
                db_context.close()
        try:
            delivered = send_payment_success_to_n8n(payload)
        except Exception as exc:  # pragma: no cover - defensive
            delivered = False
            error = type(exc).__name__
        else:
            error = None if delivered else "n8n delivery failed"
        with SessionLocal() if request_db is None else nullcontext(request_db) as db:
            current = db.get(models.NotificationOutbox, notification_id)
            if not current:
                continue
            if delivered:
                current.status = models.NotificationStatus.SENT
                current.sent_at = datetime.now(timezone.utc)
                current.last_error = None
            else:
                current.status = models.NotificationStatus.FAILED
                current.last_error = error
                current.next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=min(3600, 2 ** min(current.attempt_count, 10)))
            db.commit()
            processed += 1
    return processed


def enqueue_automation_event(
    db: Session,
    participant: models.Participant,
    event_type: str,
    idempotency_key: str,
    extra_payload: dict | None = None,
) -> models.NotificationOutbox:
    payload = payment_payload(db, participant)
    payload.update(extra_payload or {})
    payload.update({
        "event_type": event_type,
        "event_version": 1,
        "idempotency_key": idempotency_key,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
    })
    item = models.NotificationOutbox(
        idempotency_key=idempotency_key,
        participant_id=participant.id,
        event_type=event_type,
        payload=json.dumps(payload),
        status=models.NotificationStatus.PENDING,
    )
    db.add(item)
    db.flush()
    return item


def automation_event_response(item: models.NotificationOutbox) -> dict:
    return {
        "id": item.id,
        "event_type": item.event_type,
        "participant_id": item.participant_id,
        "status": item.status.value,
        "attempt_count": item.attempt_count,
        "last_error": item.last_error,
        "next_retry_at": item.next_retry_at,
        "sent_at": item.sent_at,
    }


def require_successful_participant(db: Session, participant_id: int) -> models.Participant:
    participant = db.get(models.Participant, participant_id)
    if not participant:
        raise HTTPException(status_code=404, detail="Participant not found")
    if participant.payment_status != models.PaymentStatus.SUCCESS:
        raise HTTPException(status_code=409, detail="Automation is available only after verified payment")
    return participant


def dispatch_outbox_event(db: Session, item: models.NotificationOutbox) -> dict:
    db.commit()
    process_pending_notifications(request_db=db)
    db.refresh(item)
    return automation_event_response(item)


@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok", "message": "Workshop registration API is running"}


@app.get("/public-config", tags=["Public configuration"])
def public_config(response: Response, db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store, max-age=0"
    branding = branding_settings_payload(db)
    return {
        key: branding[key]
        for key in (
            "brand_name",
            "brand_mark",
            "brand_accent_color",
            "instructor_name",
            "instructor_title",
            "instructor_bio",
            "instructor_email",
            "registration_roles",
            "privacy_policy_url",
            "registration_terms_url",
        )
    }


@app.get("/admin/branding", response_model=schemas.BrandingSettingsResponse, tags=["Admin"])
def get_admin_branding(_: str = Depends(require_admin), db: Session = Depends(get_db)):
    return branding_settings_payload(db)


@app.put("/admin/branding", response_model=schemas.BrandingSettingsResponse, tags=["Admin"])
def update_admin_branding(
    payload: schemas.BrandingSettingsUpdate,
    admin: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    branding = db.get(models.BrandingSettings, 1)
    if branding is None:
        branding = models.BrandingSettings(id=1)
        db.add(branding)
    for field in (
        "brand_name",
        "brand_mark",
        "brand_accent_color",
        "instructor_name",
        "instructor_title",
        "instructor_bio",
        "instructor_email",
    ):
        setattr(branding, field, str(getattr(payload, field)))
    branding.registration_roles = json.dumps(payload.registration_roles)
    branding.updated_by = admin
    branding.updated_at = datetime.now(timezone.utc)
    try:
        db.commit()
    except OperationalError as exc:
        db.rollback()
        raise HTTPException(
            status_code=503,
            detail="Database is temporarily busy. Please retry saving in a moment.",
        ) from exc
    db.refresh(branding)
    return branding_settings_payload(db)


def public_workshop_payload(db: Session, workshop: models.Workshop) -> dict:
    paid = confirmed_seat_count(db)
    learning_points = json.loads(workshop.learning_points or "[]")
    sold_out = paid >= workshop.max_seats
    status_open = workshop.registration_status == models.RegistrationStatus.REGISTRATION_OPEN
    production_ready = _production_registration_ready(db)
    registration_open = status_open and not sold_out and production_ready
    if sold_out:
        registration_message = "This workshop is fully booked."
    elif not status_open:
        registration_message = "Registration is currently closed."
    elif not production_ready:
        registration_message = (
            "Online registration is temporarily unavailable while the organizer "
            "completes launch setup. Please check back later."
        )
    else:
        registration_message = None
    return {
        "name": workshop.workshop_name,
        "date": workshop.workshop_date,
        "start_time": workshop.start_time,
        "end_time": workshop.end_time,
        "time": f"{workshop.start_time} – {workshop.end_time}",
        "mode": workshop.mode,
        "price": workshop.price_paise // 100,
        "currency": "INR",
        "max_seats": workshop.max_seats,
        "confirmed_seats": paid,
        "available_seats": max(0, workshop.max_seats - paid),
        "registration_open": registration_open,
        "registration_message": registration_message,
        "registration_status": workshop.registration_status,
        "slug": workshop.slug,
        "timezone": workshop.timezone,
        "description": workshop.description,
        "learning_points": learning_points,
    }


@app.get("/workshop", response_model=schemas.WorkshopResponse, tags=["Workshop"])
def workshop_info(response: Response, db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store, max-age=0"
    return public_workshop_payload(db, get_workshop(db))


@app.post("/register", response_model=schemas.PublicParticipantResponse, status_code=201, tags=["Registration"])
def register_participant(payload: schemas.ParticipantCreate, db: Session = Depends(get_db)):
    if not _production_registration_ready(db):
        raise HTTPException(status_code=503, detail="Registration is temporarily unavailable while required production setup is incomplete")
    workshop = get_workshop(db)
    if workshop.registration_status != models.RegistrationStatus.REGISTRATION_OPEN:
        raise HTTPException(status_code=409, detail="Registration is currently closed")
    allowed_roles = branding_settings_payload(db)["registration_roles"]
    if payload.role not in allowed_roles:
        raise HTTPException(
            status_code=422,
            detail=[{
                "loc": ["body", "role"],
                "msg": f"Choose a role from the available options: {', '.join(allowed_roles)}",
                "type": "value_error",
            }],
        )
    normalized_email = str(payload.email).strip().lower()
    normalized_whatsapp = payload.whatsapp

    email_match = (
        db.query(models.Participant)
        .filter(func.lower(models.Participant.email) == normalized_email, models.Participant.workshop == workshop.workshop_name)
        .first()
    )
    whatsapp_match = None
    if not email_match:
        whatsapp_match = (
            db.query(models.Participant)
            .filter(models.Participant.whatsapp.in_(schemas.whatsapp_lookup_values(normalized_whatsapp)), models.Participant.workshop == workshop.workshop_name)
            .first()
        )
    existing = email_match or whatsapp_match
    if existing:
        if existing.payment_status == models.PaymentStatus.SUCCESS:
            if email_match:
                raise HTTPException(status_code=409, detail="This email address is already registered for this workshop")
            raise HTTPException(status_code=409, detail="This WhatsApp number is already registered for this workshop")
        return existing

    if confirmed_seat_count(db) >= workshop.max_seats:
        raise HTTPException(status_code=409, detail="Registration is closed because all seats are filled")

    payment_token = create_payment_token()
    participant = models.Participant(
        name=payload.name,
        email=normalized_email,
        whatsapp=normalized_whatsapp,
        role=payload.role,
        experience=payload.experience,
        workshop=workshop.workshop_name,
        amount_paise=workshop.price_paise,
        payment_status=models.PaymentStatus.PENDING,
        payment_token_hash=token_hash(payment_token),
    )
    try:
        seat_count = int(
            db.execute(text("SELECT COUNT(*) FROM participants WHERE payment_status = 'SUCCESS' AND workshop = :workshop"), {"workshop": workshop.workshop_name}).scalar() or 0
        )
        if seat_count >= workshop.max_seats:
            raise HTTPException(status_code=409, detail="Registration is closed because all seats are filled")
        db.add(participant)
        db.flush()
        db.commit()
        db.refresh(participant)
        return schemas.PublicParticipantResponse(
            id=participant.id,
            workshop=participant.workshop,
            amount=participant.amount,
            payment_status=participant.payment_status,
            registered_at=participant.registered_at,
            payment_token=payment_token,
        )
    except HTTPException:
        db.rollback()
        raise
    except (IntegrityError, SQLAlchemyError) as exc:
        db.rollback()
        if isinstance(exc, IntegrityError):
            raise HTTPException(status_code=409, detail="You are already registered for this workshop.") from exc
        raise HTTPException(status_code=500, detail="Could not save registration") from exc




@app.get("/participants", response_model=List[schemas.ParticipantResponse], tags=["Admin"])
def get_all_participants(_: str = Depends(require_admin), db: Session = Depends(get_db)):
    return db.query(models.Participant).order_by(models.Participant.id).all()


@app.get("/participants/{participant_id}", response_model=schemas.ParticipantResponse, tags=["Admin"])


def get_participant(participant_id: int, _: str = Depends(require_admin), db: Session = Depends(get_db)):
    participant = db.query(models.Participant).filter(models.Participant.id == participant_id).first()
    if not participant:
        raise HTTPException(status_code=404, detail="Participant not found")
    return participant


@app.get("/admin/automation/events", tags=["Admin automation"])
def list_automation_events(
    _: str = Depends(require_admin),
    db: Session = Depends(get_db),
    limit: int = Query(default=100, ge=1, le=200),
):
    events = (
        db.query(models.NotificationOutbox)
        .order_by(models.NotificationOutbox.id.desc())
        .limit(limit)
        .all()
    )
    return [automation_event_response(item) for item in events]


@app.get("/admin/automation/status", tags=["Admin automation"])
def automation_status(_: str = Depends(require_admin), db: Session = Depends(get_db)):
    return {
        "webhook_configured": bool(AUTOMATION_WEBHOOK_URL),
        "pending": db.query(models.NotificationOutbox).filter(
            models.NotificationOutbox.status == models.NotificationStatus.PENDING
        ).count(),
        "failed": db.query(models.NotificationOutbox).filter(
            models.NotificationOutbox.status == models.NotificationStatus.FAILED
        ).count(),
        "sent": db.query(models.NotificationOutbox).filter(
            models.NotificationOutbox.status == models.NotificationStatus.SENT
        ).count(),
        "accepted_event_types": [
            "payment.success",
            "workflow.trigger",
            "reminder.schedule",
        ],
    }


@app.get("/admin/product/readiness", tags=["Admin product setup"])
def product_readiness(_: str = Depends(require_admin), db: Session = Depends(get_db)):
    branding = branding_settings_payload(db)
    workshop = get_workshop(db)
    payment_keys_configured = bool(RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET)
    payment_is_live = RAZORPAY_KEY_ID.startswith("rzp_live_")
    valid_branding = (
        branding["brand_name"].strip().lower() not in {"", "build the web", "your brand"}
        and branding["instructor_name"].strip().lower() not in {"", "your name", "your workshop instructor"}
        and branding["instructor_title"].strip().lower() not in {"", "workshop facilitator", "your title"}
        and len(branding["instructor_bio"].strip()) >= 40
        and "example.com" not in branding["instructor_email"].lower()
        and "your.email" not in branding["instructor_email"].lower()
        and bool(re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", branding["instructor_email"].strip()))
    )
    policies_configured = all(
        url.startswith("https://")
        for url in (settings.privacy_policy_url, settings.registration_terms_url)
    )
    admin_credentials_adequate = (
        bool(settings.admin_username)
        and settings.admin_username.lower() not in {"admin", "administrator"}
        and len(settings.admin_password) >= 16
    )
    try:
        datetime.strptime(workshop.workshop_date, "%Y-%m-%d")
        valid_workshop_date = True
    except ValueError:
        valid_workshop_date = False
    valid_workshop = (
        valid_workshop_date
        and workshop.registration_status == models.RegistrationStatus.REGISTRATION_OPEN
        and bool(workshop.workshop_name.strip())
    )
    production_origins = bool(settings.frontend_origins) and all(
        origin.lower().startswith("https://") and "*" not in origin
        for origin in settings.frontend_origins
    )
    database_is_persistent = engine.dialect.name not in {"sqlite"}

    checks = [
        {
            "key": "branding",
            "label": "Brand and instructor profile",
            "status": "ready" if valid_branding else "action_required",
            "required": True,
            "detail": "Public brand and instructor details are personalized."
            if valid_branding else "Replace the starter brand and instructor placeholders.",
        },
        {
            "key": "admin",
            "label": "Owner admin credentials",
            "status": "ready" if admin_credentials_adequate else "action_required",
            "required": True,
            "detail": "A non-default admin username and long password are configured."
            if admin_credentials_adequate
            else "Set a non-default ADMIN_USERNAME and a unique ADMIN_PASSWORD of at least 16 characters.",
        },
        {
            "key": "admin_rate_limiting",
            "label": "Admin edge rate limiting",
            "status": "ready" if settings.admin_rate_limiting_configured else "warning",
            "required": True,
            "detail": "The owner confirms rate limiting is configured in front of the admin API."
            if settings.admin_rate_limiting_configured else "Configure edge rate limiting for the admin API before launch; then set ADMIN_RATE_LIMITING_CONFIGURED=true.",
        },
        {
            "key": "payment",
            "label": "Payment account",
            "status": "ready" if payment_is_live else "warning" if payment_keys_configured else "action_required",
            "required": True,
            "detail": "Live payment credentials are configured."
            if payment_is_live else "Test credentials are configured; switch to live credentials before accepting real payments."
            if payment_keys_configured else "Add payment-provider credentials to the server environment.",
        },
        {
            "key": "payment_webhook",
            "label": "Payment signature verification",
            "status": "ready" if RAZORPAY_WEBHOOK_SECRET else "action_required",
            "required": True,
            "detail": "Payment webhook signature secret is configured."
            if RAZORPAY_WEBHOOK_SECRET else "Configure the payment webhook signing secret on the server.",
        },
        {
            "key": "database",
            "label": "Production database",
            "status": "ready" if database_is_persistent else "warning",
            "required": True,
            "detail": f"Connected to {engine.dialect.name}."
            if database_is_persistent else "SQLite is suitable for local development; use a managed database for production.",
        },
        {
            "key": "workshop",
            "label": "Workshop ready to publish",
            "status": "ready" if valid_workshop else "action_required",
            "required": True,
            "detail": "A dated workshop is open for registration."
            if valid_workshop else "Set the schedule and open registration in workshop settings.",
        },
        {
            "key": "policies",
            "label": "Privacy and registration policies",
            "status": "ready" if policies_configured else "action_required",
            "required": True,
            "detail": "HTTPS privacy and registration terms pages are configured."
            if policies_configured else "Publish and configure HTTPS privacy and registration terms URLs before collecting attendee data or payments.",
        },
        {
            "key": "backups",
            "label": "Database backups and restore test",
            "status": "ready" if settings.data_backups_verified else "warning",
            "required": True,
            "detail": "The owner confirms a backup and restore test has been completed."
            if settings.data_backups_verified else "Configure automated database backups and verify a restore before launch; then set DATA_BACKUPS_VERIFIED=true.",
        },
        {
            "key": "monitoring",
            "label": "Production monitoring and alerts",
            "status": "ready" if settings.production_monitoring_configured else "warning",
            "required": True,
            "detail": "The owner confirms production monitoring and alerts are configured."
            if settings.production_monitoring_configured else "Configure service and payment-failure monitoring before launch; then set PRODUCTION_MONITORING_CONFIGURED=true.",
        },
        {
            "key": "payment_operations",
            "label": "Payment reconciliation and refund process",
            "status": "ready" if settings.payment_operations_reviewed else "warning",
            "required": True,
            "detail": "The owner confirms a payment reconciliation and refund process is documented."
            if settings.payment_operations_reviewed else "Document how to reconcile payments and handle cancellation/refund requests; this app does not automate refunds. Then set PAYMENT_OPERATIONS_REVIEWED=true.",
        },
        {
            "key": "production",
            "label": "HTTPS production deployment",
            "status": "ready" if settings.app_env == "production" and production_origins else "warning",
            "required": True,
            "detail": "Production mode and explicit HTTPS origins are configured."
            if settings.app_env == "production" and production_origins
            else "Set APP_ENV=production and configure explicit HTTPS frontend origins before launch.",
        },
        {
            "key": "automation",
            "label": "Automation webhook",
            "status": "ready" if AUTOMATION_WEBHOOK_URL else "warning",
            "required": False,
            "detail": "Automation endpoint is configured."
            if AUTOMATION_WEBHOOK_URL else "Optional: set AUTOMATION_WEBHOOK_URL to connect reminders and follow-up workflows.",
        },
    ]
    required_checks = [item for item in checks if item["required"]]
    required_unresolved_count = sum(item["status"] != "ready" for item in required_checks)
    return {
        "go_live_ready": required_unresolved_count == 0,
        "required_unresolved_count": required_unresolved_count,
        "action_required_count": sum(item["status"] == "action_required" for item in checks),
        "warning_count": sum(item["status"] == "warning" for item in checks),
        "ready_count": sum(item["status"] == "ready" for item in checks),
        "check_count": len(checks),
        "checks": checks,
    }


@app.post("/admin/participants/{participant_id}/automation/initiate", tags=["Admin automation"])
def initiate_participant_automation(
    participant_id: int,
    _: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    participant = require_successful_participant(db, participant_id)
    idempotency_key = f"workflow.trigger:{participant.id}"
    item = db.query(models.NotificationOutbox).filter(
        models.NotificationOutbox.idempotency_key == idempotency_key
    ).first()
    if item:
        if item.status == models.NotificationStatus.SENT:
            return automation_event_response(item)
        if item.status == models.NotificationStatus.PROCESSING:
            raise HTTPException(status_code=409, detail="Workflow is already being delivered")
        if item.status == models.NotificationStatus.FAILED:
            item.status = models.NotificationStatus.PENDING
            item.next_retry_at = datetime.now(timezone.utc)
            item.last_error = None
        result = dispatch_outbox_event(db, item)
    else:
        try:
            item = enqueue_automation_event(
                db,
                participant,
                "workflow.trigger",
                idempotency_key,
            )
        except IntegrityError:
            db.rollback()
            item = db.query(models.NotificationOutbox).filter(
                models.NotificationOutbox.idempotency_key == idempotency_key
            ).one()
        result = dispatch_outbox_event(db, item)
    if result["status"] != models.NotificationStatus.SENT.value:
        raise HTTPException(
            status_code=502,
            detail={
                "message": "Workflow event was queued but could not be delivered. It will be retried.",
                "event": result,
            },
        )
    return result


@app.post("/admin/participants/{participant_id}/reminder/schedule", tags=["Admin automation"])
def schedule_participant_reminder(
    participant_id: int,
    _: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    participant = require_successful_participant(db, participant_id)
    workshop = db.query(models.Workshop).filter(
        models.Workshop.workshop_name == participant.workshop
    ).first()
    if not workshop:
        raise HTTPException(status_code=404, detail="Workshop configuration not found")
    try:
        workshop_date = datetime.strptime(workshop.workshop_date, "%Y-%m-%d").date()
        try:
            start_time = datetime.strptime(workshop.start_time, "%H:%M").time()
        except ValueError:
            start_time = datetime.strptime(workshop.start_time, "%I:%M %p").time()
        event_timezone = ZoneInfo(workshop.timezone)
    except (ValueError, ZoneInfoNotFoundError) as exc:
        raise HTTPException(status_code=422, detail="Workshop date, time, or timezone is invalid") from exc

    send_at = datetime.combine(workshop_date, start_time, tzinfo=event_timezone) - timedelta(hours=24)
    now = datetime.now(timezone.utc)
    if send_at <= now:
        raise HTTPException(status_code=409, detail="The 24-hour reminder time has already passed")

    idempotency_key = f"reminder.24h:{participant.id}:{send_at.astimezone(timezone.utc).isoformat()}"
    item = db.query(models.NotificationOutbox).filter(
        models.NotificationOutbox.idempotency_key == idempotency_key
    ).first()
    if item and item.status == models.NotificationStatus.SENT:
        return automation_event_response(item)
    if item and item.status == models.NotificationStatus.PROCESSING:
        raise HTTPException(status_code=409, detail="Reminder is already being scheduled")
    if not item:
        try:
            item = enqueue_automation_event(
                db,
                participant,
                "reminder.schedule",
                idempotency_key,
                {
                    "reminder_type": "24_hours_before",
                    "scheduled_for": send_at.astimezone(timezone.utc).isoformat(),
                    "scheduled_timezone": workshop.timezone,
                    "email_template": "workshop_reminder",
                },
            )
        except IntegrityError:
            db.rollback()
            item = db.query(models.NotificationOutbox).filter(
                models.NotificationOutbox.idempotency_key == idempotency_key
            ).one()
    result = dispatch_outbox_event(db, item)
    if result["status"] != models.NotificationStatus.SENT.value:
        raise HTTPException(
            status_code=502,
            detail={
                "message": "Reminder schedule was queued but could not be delivered. It will be retried.",
                "event": result,
            },
        )
    return result


@app.post("/admin/participants/{participant_id}/email-draft", tags=["Admin automation"])
def draft_participant_email(
    participant_id: int,
    template: str = "workshop_reminder",
    _: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if template not in {"registration_confirmation", "workshop_reminder", "payment_receipt"}:
        raise HTTPException(status_code=422, detail="Unsupported email template")
    participant = require_successful_participant(db, participant_id)
    workshop = db.query(models.Workshop).filter(
        models.Workshop.workshop_name == participant.workshop
    ).first()
    if not workshop:
        raise HTTPException(status_code=404, detail="Workshop configuration not found")
    if template == "payment_receipt":
        subject = f"Payment receipt: {workshop.workshop_name}"
        opening = f"Your payment of INR {participant.amount} has been verified."
    elif template == "registration_confirmation":
        subject = f"You're registered: {workshop.workshop_name}"
        opening = "Your payment is verified and your workshop registration is confirmed."
    else:
        subject = f"Reminder: {workshop.workshop_name}"
        opening = "This is a reminder about your upcoming workshop."

    meeting_details = ""
    if workshop.meeting_url:
        meeting_details = f"\nJoin here: {workshop.meeting_url}"
    if workshop.meeting_id:
        meeting_details += f"\nMeeting ID: {workshop.meeting_id}"
    body = (
        f"Hi {participant.name},\n\n{opening}\n\n"
        f"Workshop: {workshop.workshop_name}\n"
        f"Date: {workshop.workshop_date}\n"
        f"Time: {workshop.start_time}–{workshop.end_time} ({workshop.timezone})"
        f"{meeting_details}\n\n"
        "If you have questions, reply to this email.\n"
    )
    return {
        "to": participant.email,
        "subject": subject,
        "body": body,
        "template": template,
        "sent": False,
        "note": "Draft only. Connect an email provider in your automation workflow to send it.",
    }


@app.post("/admin/automation/events/{event_id}/retry", tags=["Admin automation"])
def retry_automation_event(
    event_id: int,
    _: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    item = db.get(models.NotificationOutbox, event_id)
    if not item:
        raise HTTPException(status_code=404, detail="Automation event not found")
    if item.status == models.NotificationStatus.SENT:
        return automation_event_response(item)
    if item.status == models.NotificationStatus.PROCESSING:
        raise HTTPException(status_code=409, detail="Automation event is already being delivered")
    item.status = models.NotificationStatus.PENDING
    item.next_retry_at = datetime.now(timezone.utc)
    item.last_error = None
    result = dispatch_outbox_event(db, item)
    if result["status"] != models.NotificationStatus.SENT.value:
        raise HTTPException(
            status_code=502,
            detail={"message": "Automation retry failed and will be retried.", "event": result},
        )
    return result


@app.post("/payment/create", response_model=schemas.PaymentCreateResponse, tags=["Payment"])
def create_payment(payload: schemas.PaymentCreateRequest, db: Session = Depends(get_db)):
    if not _production_registration_ready(db):
        raise HTTPException(status_code=503, detail="Checkout is temporarily unavailable while required production setup is incomplete")
    participant = db.query(models.Participant).filter(models.Participant.id == payload.participant_id).first()
    if not participant:
        raise HTTPException(status_code=404, detail="Participant not found")
    if not participant.payment_token_hash or not secrets.compare_digest(participant.payment_token_hash, token_hash(payload.payment_token)):
        raise HTTPException(status_code=403, detail="Invalid payment session")
    if participant.payment_status == models.PaymentStatus.SUCCESS:
        raise HTTPException(status_code=409, detail="Payment has already been completed")
    workshop = db.query(models.Workshop).filter(models.Workshop.workshop_name == participant.workshop).first() or get_workshop(db)
    if workshop.registration_status != models.RegistrationStatus.REGISTRATION_OPEN:
        raise HTTPException(status_code=409, detail="Registration is currently closed")
    if confirmed_seat_count(db) >= workshop.max_seats:
        raise HTTPException(status_code=409, detail="Registration is closed because all seats are filled")

    try:
        order = create_razorpay_order(participant.amount_paise, f"participant_{participant.id}")
        participant.razorpay_order_id = order["id"]
        participant.payment_status = models.PaymentStatus.PENDING
        db.add(models.PaymentAttempt(
            participant_id=participant.id,
            razorpay_order_id=order["id"],
            amount_paise=participant.amount_paise,
            status=models.PaymentStatus.PENDING,
        ))
        db.commit()
    except RuntimeError as exc:
        db.rollback()
        raise HTTPException(status_code=502, detail="Payment provider order creation failed") from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail="Could not save payment order") from exc

    return schemas.PaymentCreateResponse(
        razorpay_order_id=order["id"],
        amount=participant.amount,
        currency="INR",
        key_id=RAZORPAY_KEY_ID,
        participant_id=participant.id,
    )


@app.post("/payment/verify", response_model=schemas.PaymentVerifyResponse, tags=["Payment"])
def verify_payment(payload: schemas.PaymentVerifyRequest, db: Session = Depends(get_db)):
    if not payload.razorpay_order_id or not payload.razorpay_payment_id or not payload.razorpay_signature:
        raise HTTPException(status_code=400, detail="Missing payment verification fields")
    participant = db.query(models.Participant).filter(models.Participant.razorpay_order_id == payload.razorpay_order_id).first()
    if not participant:
        raise HTTPException(status_code=404, detail="Payment order not found")
    if participant.payment_status == models.PaymentStatus.SUCCESS:
        process_pending_notifications(request_db=db)
        return schemas.PaymentVerifyResponse(success=True, message="Payment already verified", participant=participant)
    if not verify_razorpay_signature(payload.razorpay_order_id, payload.razorpay_payment_id, payload.razorpay_signature):
        raise HTTPException(status_code=400, detail="Payment verification failed")
    attempt = db.query(models.PaymentAttempt).filter(
        models.PaymentAttempt.participant_id == participant.id,
        models.PaymentAttempt.razorpay_order_id == payload.razorpay_order_id,
    ).first()
    if not attempt:
        raise HTTPException(status_code=400, detail="Payment attempt not found")
    validate_provider_payment(db, participant, attempt, payload.razorpay_payment_id)
    participant = mark_payment_success(db, participant, payload.razorpay_payment_id)
    process_pending_notifications(request_db=db)
    return schemas.PaymentVerifyResponse(success=True, message="Payment verified successfully", participant=participant)


@app.post("/payment/webhook", tags=["Payment"])
async def payment_webhook(request: Request, db: Session = Depends(get_db)):
    body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")
    if not verify_razorpay_webhook_signature(body, signature):
        raise HTTPException(status_code=400, detail="Invalid webhook signature")
    try:
        event = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid webhook payload") from exc

    event_name = str(event.get("event", ""))
    provider_event_id = str(event.get("id") or hashlib.sha256(body).hexdigest())
    existing_event = db.query(models.WebhookEvent).filter(models.WebhookEvent.provider_event_id == provider_event_id).first()
    if existing_event:
        return {"received": True, "processed": existing_event.status == "PROCESSED", "duplicate": True}
    webhook_record = models.WebhookEvent(provider_event_id=provider_event_id, event_type=event_name, status="PROCESSING")
    db.add(webhook_record)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return {"received": True, "processed": True, "duplicate": True}
    payment_entity = event.get("payload", {}).get("payment", {}).get("entity", {})
    order_entity = event.get("payload", {}).get("order", {}).get("entity", {})
    order_id = payment_entity.get("order_id") or order_entity.get("id")
    payment_id = payment_entity.get("id")
    if not order_id:
        webhook_record.status = "IGNORED"
        webhook_record.processed_at = datetime.now(timezone.utc)
        db.commit()
        return {"received": True, "processed": False}

    attempt = db.query(models.PaymentAttempt).filter(models.PaymentAttempt.razorpay_order_id == order_id).first()
    participant = db.query(models.Participant).filter(models.Participant.razorpay_order_id == order_id).first()
    if not participant or not attempt:
        webhook_record.status = "IGNORED"
        webhook_record.processed_at = datetime.now(timezone.utc)
        db.commit()
        return {"received": True, "processed": False}
    webhook_record.participant_id = participant.id
    webhook_record.payment_attempt_id = attempt.id

    if event_name in {"payment.captured", "order.paid"} and payment_id:
        if participant.payment_status == models.PaymentStatus.SUCCESS:
            webhook_record.status = "PROCESSED"
            webhook_record.processed_at = datetime.now(timezone.utc)
            db.commit()
            return {"received": True, "processed": True, "status": "SUCCESS"}
        try:
            validate_provider_payment(db, participant, attempt, payment_id)
            participant = mark_payment_success(db, participant, payment_id)
            webhook_record = db.query(models.WebhookEvent).filter(models.WebhookEvent.provider_event_id == provider_event_id).one()
            webhook_record.status = "PROCESSED"
            webhook_record.processed_at = datetime.now(timezone.utc)
            db.commit()
            process_pending_notifications(request_db=db)
        except HTTPException:
            db.rollback()
            webhook_record = db.query(models.WebhookEvent).filter(models.WebhookEvent.provider_event_id == provider_event_id).one_or_none()
            if webhook_record:
                webhook_record.status = "REJECTED"
                webhook_record.processed_at = datetime.now(timezone.utc)
                db.commit()
            raise
        return {"received": True, "processed": True, "status": participant.payment_status.value}

    if event_name == "payment.failed" and participant.payment_status == models.PaymentStatus.PENDING:
        participant.payment_status = models.PaymentStatus.FAILED
        attempt = db.query(models.PaymentAttempt).filter(models.PaymentAttempt.razorpay_order_id == order_id).first()
        if attempt:
            attempt.status = models.PaymentStatus.FAILED
        webhook_record.status = "PROCESSED"
        webhook_record.processed_at = datetime.now(timezone.utc)
        db.commit()
    else:
        webhook_record.status = "PROCESSED"
        webhook_record.processed_at = datetime.now(timezone.utc)
        db.commit()
    return {"received": True, "processed": True}


def _workshop_admin_payload(db: Session, workshop: models.Workshop) -> dict:
    payload = public_workshop_payload(db, workshop)
    payload.update({
        "meeting_platform": workshop.meeting_platform,
        "meeting_id": workshop.meeting_id,
        "meeting_url": workshop.meeting_url,
        "updated_at": workshop.updated_at,
        "updated_by": workshop.updated_by,
    })
    return payload


def _workshop_edit_values(workshop: models.Workshop) -> dict:
    return {
        "workshop_name": workshop.workshop_name,
        "slug": workshop.slug,
        "workshop_date": workshop.workshop_date,
        "start_time": workshop.start_time,
        "end_time": workshop.end_time,
        "timezone": workshop.timezone,
        "price_paise": workshop.price_paise,
        "max_seats": workshop.max_seats,
        "registration_status": workshop.registration_status.value,
        "description": workshop.description,
        "mode": workshop.mode,
        "learning_points": json.loads(workshop.learning_points or "[]"),
        "meeting_platform": workshop.meeting_platform,
        "meeting_id": workshop.meeting_id,
        "meeting_url": workshop.meeting_url,
    }


@app.get("/admin/workshop", response_model=schemas.WorkshopAdminResponse, tags=["Admin"])
def admin_workshop(_: str = Depends(require_admin), db: Session = Depends(get_db)):
    workshop = get_workshop(db)
    return _workshop_admin_payload(db, workshop)


@app.put("/admin/workshop", response_model=schemas.WorkshopAdminResponse, tags=["Admin"])
def update_admin_workshop(payload: schemas.WorkshopAdminUpdate, admin: str = Depends(require_admin), db: Session = Depends(get_db)):
    if payload.end_time <= payload.start_time:
        raise HTTPException(status_code=422, detail="End time must be after start time")
    try:
        ZoneInfo(payload.timezone)
    except ZoneInfoNotFoundError as exc:
        if payload.timezone not in {"UTC", "Asia/Kolkata", "Asia/Calcutta", "Europe/London", "America/New_York", "America/Los_Angeles"}:
            raise HTTPException(status_code=422, detail="Invalid timezone") from exc
    workshop = get_workshop(db)
    old_name = workshop.workshop_name
    old_values = _workshop_edit_values(workshop)
    for field in ("workshop_name", "slug", "workshop_date", "start_time", "end_time", "timezone", "price_paise", "max_seats", "registration_status", "description", "mode", "meeting_platform", "meeting_id", "meeting_url"):
        setattr(workshop, field, getattr(payload, field))
    workshop.learning_points = json.dumps(payload.learning_points)
    workshop.updated_by = admin
    workshop.updated_at = datetime.now(timezone.utc)
    if old_name != workshop.workshop_name:
        db.query(models.Participant).filter(
            models.Participant.workshop == old_name
        ).update({models.Participant.workshop: workshop.workshop_name}, synchronize_session=False)
    counter = db.query(models.SeatCounter).filter(models.SeatCounter.workshop == old_name).one_or_none()
    if counter:
        counter.workshop = workshop.workshop_name
        counter.max_seats = workshop.max_seats
    db.add(models.WorkshopAudit(
        workshop_id=workshop.id,
        changed_by=admin,
        old_values=json.dumps(old_values),
        new_values=json.dumps(_workshop_edit_values(workshop)),
    ))
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Workshop slug is already in use") from exc
    except OperationalError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail="Database is temporarily busy. Please retry saving in a moment.") from exc
    db.refresh(workshop)
    return _workshop_admin_payload(db, workshop)


@app.get("/admin/workshop/stats", response_model=schemas.WorkshopStatsResponse, tags=["Admin"])
def admin_workshop_stats(_: str = Depends(require_admin), db: Session = Depends(get_db)):
    workshop = get_workshop(db)
    rows = db.query(models.Participant).filter(models.Participant.workshop == workshop.workshop_name).all()
    paid = sum(row.payment_status == models.PaymentStatus.SUCCESS for row in rows)
    return {
        "workshop_name": workshop.workshop_name,
        "registration_status": workshop.registration_status,
        "max_seats": workshop.max_seats,
        "registered_count": len(rows),
        "paid_count": paid,
        "available_seats": max(0, workshop.max_seats - paid),
        "pending_payments": sum(row.payment_status == models.PaymentStatus.PENDING for row in rows),
        "failed_payments": sum(row.payment_status == models.PaymentStatus.FAILED for row in rows),
    }


@app.get("/admin/workshop/history", response_model=List[schemas.WorkshopAuditResponse], tags=["Admin"])
def admin_workshop_history(_: str = Depends(require_admin), db: Session = Depends(get_db)):
    audits = db.query(models.WorkshopAudit).order_by(models.WorkshopAudit.changed_at.desc()).limit(100).all()
    return [{"id": item.id, "changed_at": item.changed_at, "changed_by": item.changed_by, "old_values": json.loads(item.old_values), "new_values": json.loads(item.new_values)} for item in audits]


@app.get("/admin/participants/export", tags=["Admin"])
def export_participants_csv(_: str = Depends(require_admin), db: Session = Depends(get_db)):
    workshop = get_workshop(db)
    rows = db.query(models.Participant).filter(models.Participant.workshop == workshop.workshop_name).order_by(models.Participant.id).all()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "id",
        "name",
        "email",
        "whatsapp",
        "role",
        "experience",
        "workshop",
        "amount",
        "payment_status",
        "registered_at",
        "razorpay_order_id",
        "razorpay_payment_id",
    ])
    for row in rows:
        writer.writerow([
            row.id,
            row.name,
            row.email,
            row.whatsapp,
            row.role,
            row.experience,
            row.workshop,
            row.amount,
            row.payment_status.value,
            row.registered_at.isoformat() if row.registered_at else "",
            row.razorpay_order_id or "",
            row.razorpay_payment_id or "",
        ])
    filename = re.sub(r"[^a-z0-9]+", "-", workshop.workshop_name.lower()).strip("-") or "participants"
    csv_text = buffer.getvalue()
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}-participants.csv"'},
    )


@app.get("/admin/summary", tags=["Admin"])
def admin_summary(_: str = Depends(require_admin), db: Session = Depends(get_db)):
    workshop = get_workshop(db)
    rows = db.query(models.Participant).filter(models.Participant.workshop == workshop.workshop_name).all()
    successful = [row for row in rows if row.payment_status == models.PaymentStatus.SUCCESS]
    role_breakdown = {}
    for row in rows:
        role_breakdown[row.role] = role_breakdown.get(row.role, 0) + 1
    return {
        "workshop_name": workshop.workshop_name,
        "registration_status": workshop.registration_status.value,
        "max_seats": workshop.max_seats,
        "available_seats": max(0, workshop.max_seats - len(successful)),
        "total_registrations": len(rows),
        "successful_payments": len(successful),
        "pending_payments": sum(row.payment_status == models.PaymentStatus.PENDING for row in rows),
        "failed_payments": sum(row.payment_status == models.PaymentStatus.FAILED for row in rows),
        "revenue": sum(row.amount for row in successful),
        "role_breakdown": role_breakdown,
    }


@app.get("/", include_in_schema=False)
def frontend_home():
    if not HAS_PRODUCT_FRONTEND:
        return {"status": "backend-only", "message": "Frontend assets are not present in this workspace; the API is running."}
    return FileResponse(PRODUCT_INDEX)


@app.get("/events/ai-power-hour", include_in_schema=False)
@app.get("/events/full-stack-web-development", include_in_schema=False)
def full_stack_workshop_page():
    """Serve the workshop registration page at its current and legacy URLs."""
    if not HAS_FRONTEND:
        return {"status": "backend-only", "message": "Frontend assets are not present in this workspace; the API is running."}
    return FileResponse(FRONTEND_INDEX)


if HAS_ADMIN_FRONTEND:
    app.mount("/admin", StaticFiles(directory=ADMIN_DIR, html=True), name="admin_frontend")

if HAS_FRONTEND:
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
