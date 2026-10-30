import hashlib
import hmac
import json
import os
import pathlib
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from unittest import mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = pathlib.Path(__file__).resolve().parent
import sys
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("RAZORPAY_KEY_ID", "rzp_test_placeholder")
os.environ.setdefault("RAZORPAY_KEY_SECRET", "placeholder_secret")
os.environ.setdefault("RAZORPAY_WEBHOOK_SECRET", "webhook_placeholder")
os.environ.setdefault("ADMIN_USERNAME", "admin")
os.environ.setdefault("ADMIN_PASSWORD", "Str0ngPass!")
os.environ.setdefault("N8N_WEBHOOK_URL", "https://example.com/hook")

import config
import main
import models
import schemas


@pytest.fixture
def test_db():
    tmpdir = tempfile.TemporaryDirectory()
    engine = create_engine(f"sqlite:///{tmpdir.name}/test.db", connect_args={"check_same_thread": False})
    models.Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    try:
        yield Session
    finally:
        engine.dispose()
        tmpdir.cleanup()


def add_participant(Session, order_id="order_a", token="token-a", email="a@example.com", whatsapp="+918123456789"):
    with Session() as db:
        participant = models.Participant(
            name="Test User",
            email=email,
            whatsapp=whatsapp,
            role="Full-Stack Developer",
            experience="2",
            workshop=main.settings.workshop_name,
            amount_paise=39900,
            payment_status=models.PaymentStatus.PENDING,
            razorpay_order_id=order_id,
            payment_token_hash=main.token_hash(token),
        )
        db.add(participant)
        db.commit()
        db.refresh(participant)
        db.add(models.PaymentAttempt(
            participant_id=participant.id,
            razorpay_order_id=order_id,
            amount_paise=39900,
            status=models.PaymentStatus.PENDING,
        ))
        db.commit()
        return participant.id


def payment_signature(order_id="order_a", payment_id="pay_a"):
    return hmac.new(
        os.environ["RAZORPAY_KEY_SECRET"].encode(),
        f"{order_id}|{payment_id}".encode(),
        hashlib.sha256,
    ).hexdigest()


def provider_order(order_id="order_a", amount=39900, currency="INR"):
    return {"id": order_id, "amount": amount, "currency": currency}


def provider_payment(order_id="order_a", payment_id="pay_a", amount=39900, currency="INR", status="captured"):
    return {"id": payment_id, "order_id": order_id, "amount": amount, "currency": currency, "status": status}


def test_provider_validation_rejects_wrong_order_payment_amount_currency_and_status(test_db):
    participant_id = add_participant(test_db)
    with test_db() as db:
        participant = db.get(models.Participant, participant_id)
        attempt = db.query(models.PaymentAttempt).one()
        checks = [
            provider_payment(order_id="other"),
            provider_payment(payment_id="other"),
            provider_payment(amount=1),
            provider_payment(currency="USD"),
            provider_payment(status="failed"),
        ]
        for response in checks:
            with mock.patch.object(main, "fetch_razorpay_order", return_value=provider_order()), mock.patch.object(main, "fetch_razorpay_payment", return_value=response):
                with pytest.raises(Exception):
                    main.validate_provider_payment(db, participant, attempt, "pay_a")


def test_valid_signature_and_captured_provider_payment_succeed(test_db):
    participant_id = add_participant(test_db)
    original = main.app.dependency_overrides.get(main.get_db)

    def override_db():
        with test_db() as db:
            yield db

    main.app.dependency_overrides[main.get_db] = override_db
    try:
        with mock.patch.object(main, "fetch_razorpay_order", return_value=provider_order()), mock.patch.object(main, "fetch_razorpay_payment", return_value=provider_payment()), mock.patch.object(main, "send_payment_success_to_n8n", return_value=True):
            response = TestClient(main.app).post("/payment/verify", json={
                "razorpay_order_id": "order_a",
                "razorpay_payment_id": "pay_a",
                "razorpay_signature": payment_signature(),
            })
        assert response.status_code == 200
        with test_db() as db:
            assert db.get(models.Participant, participant_id).payment_status == models.PaymentStatus.SUCCESS
            assert db.query(models.Participant).one().amount_paise == 39900
    finally:
        if original is None:
            main.app.dependency_overrides.pop(main.get_db, None)
        else:
            main.app.dependency_overrides[main.get_db] = original


def test_invalid_signature_does_not_call_provider_or_succeed(test_db):
    add_participant(test_db)
    def override_db():
        with test_db() as db:
            yield db
    main.app.dependency_overrides[main.get_db] = override_db
    try:
        with mock.patch.object(main, "fetch_razorpay_order") as order_mock:
            response = TestClient(main.app).post("/payment/verify", json={"razorpay_order_id": "order_a", "razorpay_payment_id": "pay_a", "razorpay_signature": "bad"})
        assert response.status_code == 400
        order_mock.assert_not_called()
    finally:
        main.app.dependency_overrides.clear()


def test_payment_session_token_authorizes_only_matching_participant(test_db):
    first = add_participant(test_db, order_id="order_a", token="token-a")
    second = add_participant(test_db, order_id="order_b", token="token-b", email="b@example.com", whatsapp="+919876543211")
    original = main.app.dependency_overrides.get(main.get_db)
    def override_db():
        with test_db() as db:
            yield db
    main.app.dependency_overrides[main.get_db] = override_db
    try:
        with mock.patch.object(main, "create_razorpay_order", return_value={"id": "new-order"}):
            assert TestClient(main.app).post("/payment/create", json={"participant_id": first, "payment_token": "token-a"}).status_code == 200
            assert TestClient(main.app).post("/payment/create", json={"participant_id": second, "payment_token": "token-a"}).status_code == 403
            assert TestClient(main.app).post("/payment/create", json={"participant_id": first, "payment_token": "wrong"}).status_code == 403
            assert TestClient(main.app).post("/payment/create", json={"participant_id": first}).status_code == 422
    finally:
        if original is None:
            main.app.dependency_overrides.pop(main.get_db, None)
        else:
            main.app.dependency_overrides[main.get_db] = original


def test_duplicate_verification_does_not_duplicate_outbox_or_notification(test_db):
    add_participant(test_db)
    def override_db():
        with test_db() as db:
            yield db
    main.app.dependency_overrides[main.get_db] = override_db
    try:
        body = {"razorpay_order_id": "order_a", "razorpay_payment_id": "pay_a", "razorpay_signature": payment_signature()}
        with mock.patch.object(main, "fetch_razorpay_order", return_value=provider_order()), mock.patch.object(main, "fetch_razorpay_payment", return_value=provider_payment()), mock.patch.object(main, "send_payment_success_to_n8n", return_value=True) as notify:
            client = TestClient(main.app)
            assert client.post("/payment/verify", json=body).status_code == 200
            assert client.post("/payment/verify", json=body).status_code == 200
        assert notify.call_count == 1
        with test_db() as db:
            assert db.query(models.NotificationOutbox).count() == 1
    finally:
        main.app.dependency_overrides.clear()


def test_payment_retry_creates_separate_attempt(test_db):
    participant_id = add_participant(test_db, order_id="order_initial")
    with test_db() as db:
        participant = db.get(models.Participant, participant_id)
        participant.payment_status = models.PaymentStatus.PENDING
        db.commit()
    def override_db():
        with test_db() as db:
            yield db
    main.app.dependency_overrides[main.get_db] = override_db
    try:
        with mock.patch.object(main, "create_razorpay_order", side_effect=[{"id": "order_1"}, {"id": "order_2"}]):
            client = TestClient(main.app)
            assert client.post("/payment/create", json={"participant_id": participant_id, "payment_token": "token-a"}).status_code == 200
            assert client.post("/payment/create", json={"participant_id": participant_id, "payment_token": "token-a"}).status_code == 200
        with test_db() as db:
            assert db.query(models.PaymentAttempt).count() == 3
            assert db.get(models.Participant, participant_id).razorpay_order_id == "order_2"
    finally:
        main.app.dependency_overrides.clear()


def test_webhook_duplicate_is_recorded_once_and_invalid_signature_is_not_recorded(test_db):
    add_participant(test_db)
    def override_db():
        with test_db() as db:
            yield db
    main.app.dependency_overrides[main.get_db] = override_db
    body = json.dumps({"id": "evt_1", "event": "payment.captured", "payload": {"payment": {"entity": {"id": "pay_a", "order_id": "order_a"}}}})
    try:
        client = TestClient(main.app)
        with mock.patch.object(main, "verify_razorpay_webhook_signature", return_value=False):
            assert client.post("/payment/webhook", content=body, headers={"X-Razorpay-Signature": "bad"}).status_code == 400
        with test_db() as db:
            assert db.query(models.WebhookEvent).count() == 0
        with mock.patch.object(main, "verify_razorpay_webhook_signature", return_value=True), mock.patch.object(main, "fetch_razorpay_order", return_value=provider_order()), mock.patch.object(main, "fetch_razorpay_payment", return_value=provider_payment()), mock.patch.object(main, "send_payment_success_to_n8n", return_value=True) as notify:
            assert client.post("/payment/webhook", content=body).status_code == 200
            duplicate = client.post("/payment/webhook", content=body)
        assert duplicate.json()["duplicate"] is True
        assert notify.call_count == 1
        with test_db() as db:
            assert db.query(models.WebhookEvent).count() == 1
    finally:
        main.app.dependency_overrides.clear()


def test_old_payment_attempt_webhook_does_not_change_current_attempt(test_db):
    participant_id = add_participant(test_db, order_id="current_order")
    with test_db() as db:
        participant = db.get(models.Participant, participant_id)
        db.add(models.PaymentAttempt(participant_id=participant_id, razorpay_order_id="old_order", amount_paise=39900, status=models.PaymentStatus.FAILED))
        db.commit()
    body = json.dumps({"id": "evt_old", "event": "payment.captured", "payload": {"payment": {"entity": {"id": "old_pay", "order_id": "old_order"}}}})
    def override_db():
        with test_db() as db:
            yield db
    main.app.dependency_overrides[main.get_db] = override_db
    try:
        with mock.patch.object(main, "verify_razorpay_webhook_signature", return_value=True):
            response = TestClient(main.app).post("/payment/webhook", content=body)
        assert response.status_code == 200
        with test_db() as db:
            assert db.get(models.Participant, participant_id).payment_status == models.PaymentStatus.PENDING
    finally:
        main.app.dependency_overrides.clear()


def test_concurrent_duplicate_webhooks_have_one_logical_delivery(test_db):
    add_participant(test_db)
    body = json.dumps({"id": "evt_concurrent", "event": "payment.captured", "payload": {"payment": {"entity": {"id": "pay_a", "order_id": "order_a"}}}})
    def override_db():
        with test_db() as db:
            yield db
    main.app.dependency_overrides[main.get_db] = override_db
    try:
        with mock.patch.object(main, "verify_razorpay_webhook_signature", return_value=True), mock.patch.object(main, "fetch_razorpay_order", return_value=provider_order()), mock.patch.object(main, "fetch_razorpay_payment", return_value=provider_payment()), mock.patch.object(main, "send_payment_success_to_n8n", return_value=True) as notify:
            def send():
                return TestClient(main.app).post("/payment/webhook", content=body).status_code
            with ThreadPoolExecutor(max_workers=2) as pool:
                statuses = list(pool.map(lambda _: send(), range(2)))
        assert all(status == 200 for status in statuses)
        with test_db() as db:
            assert db.query(models.WebhookEvent).filter(models.WebhookEvent.provider_event_id == "evt_concurrent").count() == 1
        assert notify.call_count == 1
    finally:
        main.app.dependency_overrides.clear()


def test_webhook_provider_amount_mismatch_is_rejected(test_db):
    add_participant(test_db)
    body = json.dumps({"id": "evt_amount", "event": "payment.captured", "payload": {"payment": {"entity": {"id": "pay_a", "order_id": "order_a"}}}})
    def override_db():
        with test_db() as db:
            yield db
    main.app.dependency_overrides[main.get_db] = override_db
    try:
        with mock.patch.object(main, "verify_razorpay_webhook_signature", return_value=True), mock.patch.object(main, "fetch_razorpay_order", return_value=provider_order()), mock.patch.object(main, "fetch_razorpay_payment", return_value=provider_payment(amount=1)):
            response = TestClient(main.app).post("/payment/webhook", content=body)
        assert response.status_code == 400
        with test_db() as db:
            assert db.query(models.Participant).one().payment_status == models.PaymentStatus.PENDING
            assert db.query(models.WebhookEvent).one().status == "REJECTED"
    finally:
        main.app.dependency_overrides.clear()


def test_outbox_failure_is_retryable_and_retry_success_is_idempotent(test_db):
    participant_id = add_participant(test_db)
    with test_db() as db:
        participant = db.get(models.Participant, participant_id)
        main.enqueue_payment_notification(db, participant)
        db.commit()
        with mock.patch.object(main, "send_payment_success_to_n8n", return_value=False):
            assert main.process_pending_notifications(request_db=db) == 1
        item = db.query(models.NotificationOutbox).one()
        assert item.status == models.NotificationStatus.FAILED
        item.next_retry_at = main.datetime.now(main.timezone.utc)
        db.commit()
        with mock.patch.object(main, "send_payment_success_to_n8n", return_value=True) as notify:
            assert main.process_pending_notifications(request_db=db) == 1
            assert main.process_pending_notifications(request_db=db) == 0
            notify.assert_called_once()
        assert db.query(models.NotificationOutbox).one().status == models.NotificationStatus.SENT


def test_concurrent_outbox_retries_claim_one_delivery(test_db):
    participant_id = add_participant(test_db)
    with test_db() as db:
        main.enqueue_payment_notification(db, db.get(models.Participant, participant_id))
        db.commit()

    def process_once(_):
        with test_db() as db:
            return main.process_pending_notifications(request_db=db)

    with mock.patch.object(main, "send_payment_success_to_n8n", return_value=True) as notify:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(process_once, range(2)))
    assert sum(results) == 1
    notify.assert_called_once()
    with test_db() as db:
        assert db.query(models.NotificationOutbox).one().status == models.NotificationStatus.SENT


def test_production_cors_requires_explicit_https_origins(monkeypatch):
    monkeypatch.setenv("RAZORPAY_KEY_ID", "key")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret")
    monkeypatch.setenv("ADMIN_USERNAME", "workshop-owner")
    monkeypatch.setenv("ADMIN_PASSWORD", "a-unique-long-admin-passphrase")
    monkeypatch.setenv("DATABASE_URL", "postgresql://db")
    monkeypatch.setenv("N8N_WEBHOOK_URL", "https://n8n.example/hook")
    production = replace(
        config.settings,
        app_env="production",
        frontend_origins=("https://app.example.com",),
        admin_username="workshop-owner",
        admin_password="a-unique-long-admin-passphrase",
        privacy_policy_url="https://app.example.com/privacy",
        registration_terms_url="https://app.example.com/terms",
    )
    with mock.patch.object(config, "settings", production):
        config.validate_runtime_settings()
    with mock.patch.object(config, "settings", replace(production, frontend_origins=("http://app.example.com",))):
        with pytest.raises(RuntimeError):
            config.validate_runtime_settings()
    with mock.patch.object(config, "settings", replace(production, frontend_origins=())):
        with pytest.raises(RuntimeError):
            config.validate_runtime_settings()
    with mock.patch.object(config, "settings", replace(production, admin_password="password")):
        with pytest.raises(RuntimeError, match="16 characters"):
            config.validate_runtime_settings()
    with mock.patch.object(config, "settings", replace(production, privacy_policy_url="http://app.example.com/privacy")):
        with pytest.raises(RuntimeError, match="HTTPS"):
            config.validate_runtime_settings()


def test_simultaneous_duplicate_registration_has_one_row(test_db):
    payloads = [schemas.ParticipantCreate(
        name="Concurrent User",
        email="same@example.com",
        whatsapp="+918123456789",
        role="Full-Stack Developer",
        experience="2",
        workshop=main.settings.workshop_name,
    ) for _ in range(2)]

    def attempt(payload):
        with test_db() as db:
            try:
                return main.register_participant(payload, db).id
            except Exception as exc:
                return type(exc).__name__

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, payloads))
    with test_db() as db:
        assert db.query(models.Participant).count() == 1
    assert len(set(result for result in results if isinstance(result, int))) == 1


def test_simultaneous_final_seat_payment_allocation_cannot_exceed_limit(test_db):
    first = add_participant(test_db, order_id="seat_order_1", email="seat1@example.com", whatsapp="+919876543211")
    second = add_participant(test_db, order_id="seat_order_2", token="token-b", email="seat2@example.com", whatsapp="+919876543212")
    with test_db() as db:
        db.add(models.SeatCounter(workshop=main.settings.workshop_name, max_seats=1, allocated_seats=0))
        db.commit()

    def complete(participant_id, payment_id):
        with test_db() as db:
            try:
                main.mark_payment_success(db, db.get(models.Participant, participant_id), payment_id)
                return "success"
            except Exception as exc:
                return type(exc).__name__

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda args: complete(*args), [(first, "seat_pay_1"), (second, "seat_pay_2")]))
    with test_db() as db:
        assert db.query(models.Participant).filter(models.Participant.payment_status == models.PaymentStatus.SUCCESS).count() == 1
        assert db.query(models.SeatCounter).one().allocated_seats == 1
    assert results.count("success") == 1


def test_admin_requires_credentials_and_accepts_valid_credentials(test_db):
    def override_db():
        with test_db() as db:
            yield db
    main.app.dependency_overrides[main.get_db] = override_db
    try:
        client = TestClient(main.app)
        assert client.get("/admin/summary").status_code == 401
        assert client.get("/admin/summary", auth=("admin", "wrong")).status_code == 401
        assert client.get("/admin/summary", auth=("admin", "Str0ngPass!")).status_code == 200
    finally:
        main.app.dependency_overrides.clear()


def test_admin_branding_settings_persist_and_update_public_config(test_db):
    def override_db():
        with test_db() as db:
            yield db

    main.app.dependency_overrides[main.get_db] = override_db
    try:
        client = TestClient(main.app)
        payload = {
            "brand_name": "Northstar Workshops",
            "brand_mark": "NW",
            "brand_accent_color": "#345678",
            "instructor_name": "Alex Example",
            "instructor_title": "Workshop Facilitator",
            "instructor_bio": "A practical instructor profile for this client.",
            "instructor_email": "alex@example.com",
            "registration_roles": ["Developer", "Designer", "Founder"],
        }
        saved = client.put("/admin/branding", auth=("admin", "Str0ngPass!"), json=payload)
        assert saved.status_code == 200, saved.text
        assert saved.json()["updated_by"] == "admin"

        public = client.get("/public-config")
        assert public.status_code == 200
        assert {key: public.json()[key] for key in payload} == payload
        assert "RAZORPAY_KEY_SECRET" not in public.text
        assert "AUTOMATION_WEBHOOK_URL" not in public.text
        registration = client.post("/register", json={
            "name": "Custom Role Attendee",
            "email": "custom-role@example.com",
            "whatsapp": "+918123456789",
            "role": "Developer",
            "experience": "2",
            "workshop": main.settings.workshop_name,
        })
        assert registration.status_code == 201, registration.text
    finally:
        main.app.dependency_overrides.clear()


def test_product_readiness_reports_only_safe_configuration_status(test_db, monkeypatch):
    with test_db() as db:
        db.add(models.Workshop(
            id=1,
            workshop_name="Readiness workshop",
            slug="readiness-workshop",
            workshop_date="2027-11-24",
            start_time="16:00",
            end_time="17:00",
            timezone="Asia/Kolkata",
            price_paise=49900,
            max_seats=20,
            registration_status=models.RegistrationStatus.REGISTRATION_OPEN,
            description="Readiness test",
            mode="Online",
            learning_points="[]",
        ))
        db.commit()

    monkeypatch.setattr(main, "RAZORPAY_KEY_ID", "rzp_test_secret_identifier")
    monkeypatch.setattr(main, "RAZORPAY_KEY_SECRET", "private-payment-secret")
    monkeypatch.setattr(main, "RAZORPAY_WEBHOOK_SECRET", "private-webhook-secret")
    monkeypatch.setattr(main, "AUTOMATION_WEBHOOK_URL", "https://example.test/hook?token=private")
    monkeypatch.setattr(
        main,
        "settings",
        replace(main.settings, admin_username="admin", admin_password="private-admin-password"),
    )

    def override_db():
        with test_db() as db:
            yield db

    main.app.dependency_overrides[main.get_db] = override_db
    try:
        response = TestClient(main.app).get(
            "/admin/product/readiness",
            auth=("admin", "private-admin-password"),
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        checks = {item["key"]: item for item in payload["checks"]}
        assert checks["payment"]["status"] == "warning"
        assert checks["workshop"]["status"] == "ready"
        assert checks["automation"]["status"] == "ready"
        assert checks["policies"]["status"] == "action_required"
        assert checks["backups"]["status"] == "warning"
        assert checks["monitoring"]["status"] == "warning"
        assert payload["required_unresolved_count"] == sum(
            item["required"] and item["status"] != "ready"
            for item in payload["checks"]
        )
        assert payload["action_required_count"] == sum(
            item["status"] == "action_required" for item in payload["checks"]
        )
        assert payload["warning_count"] == sum(
            item["status"] == "warning" for item in payload["checks"]
        )
        for secret in (
            "private-payment-secret",
            "private-webhook-secret",
            "private-admin-password",
            "private",
        ):
            assert secret not in response.text
    finally:
        main.app.dependency_overrides.clear()


def test_product_readiness_does_not_accept_starter_profile_as_personalized(test_db, monkeypatch):
    with test_db() as db:
        db.add(models.Workshop(
            id=1,
            workshop_name="Readiness workshop",
            slug="readiness-workshop",
            workshop_date="2027-11-24",
            start_time="16:00",
            end_time="17:00",
            timezone="Asia/Kolkata",
            price_paise=49900,
            max_seats=20,
            registration_status=models.RegistrationStatus.REGISTRATION_OPEN,
            description="Readiness test",
            mode="Online",
            learning_points="[]",
        ))
        db.commit()
    monkeypatch.setattr(
        main,
        "settings",
        replace(
            main.settings,
            admin_username="admin",
            admin_password="private-admin-password",
            instructor_email="",
        ),
    )
    with test_db() as db:
        db.add(models.BrandingSettings(
            id=1,
            brand_name="WorkshopFlow",
            brand_mark="WF",
            brand_accent_color="#6b5bdd",
            instructor_name="Your workshop instructor",
            instructor_title="Workshop facilitator",
            instructor_bio="I help professionals turn expert knowledge into structured learning experiences.",
            instructor_email="",
            registration_roles=json.dumps(["Developer"]),
        ))
        db.commit()

    def override_db():
        with test_db() as db:
            yield db

    main.app.dependency_overrides[main.get_db] = override_db
    try:
        response = TestClient(main.app).get(
            "/admin/product/readiness",
            auth=("admin", "private-admin-password"),
        )
        assert response.status_code == 200, response.text
        checks = {item["key"]: item for item in response.json()["checks"]}
        assert checks["branding"]["status"] == "action_required"
    finally:
        main.app.dependency_overrides.clear()


def test_production_registration_is_blocked_until_readiness_passes(test_db, monkeypatch):
    monkeypatch.setattr(main, "settings", replace(main.settings, app_env="production"))
    monkeypatch.setattr(
        main,
        "product_readiness",
        lambda _admin, _db: {"go_live_ready": False},
    )

    def override_db():
        with test_db() as db:
            yield db

    main.app.dependency_overrides[main.get_db] = override_db
    try:
        client = TestClient(main.app)
        workshop = client.get("/workshop")
        assert workshop.status_code == 200
        assert workshop.json()["registration_open"] is False
        assert "completes launch setup" in workshop.json()["registration_message"]
        assert "private" not in workshop.json()["registration_message"]
        registration = client.post("/register", json={
            "name": "Blocked User",
            "email": "blocked@example.com",
            "whatsapp": "+918123456789",
            "role": "Full-Stack Developer",
            "experience": "2",
            "workshop": main.settings.workshop_name,
        })
        assert registration.status_code == 503
        assert "production setup is incomplete" in registration.json()["detail"]
        with test_db() as db:
            assert db.query(models.Participant).count() == 0
    finally:
        main.app.dependency_overrides.clear()


def test_admin_can_initiate_one_idempotent_workflow_after_payment(test_db):
    participant_id = add_participant(test_db)
    with test_db() as db:
        participant = db.get(models.Participant, participant_id)
        participant.payment_status = models.PaymentStatus.SUCCESS
        participant.payment_timestamp = main.datetime.now(main.timezone.utc)
        db.commit()

    def override_db():
        with test_db() as db:
            yield db

    main.app.dependency_overrides[main.get_db] = override_db
    try:
        client = TestClient(main.app)
        unpaid_id = add_participant(test_db, order_id="unpaid_order", token="unpaid-token", email="unpaid@example.com", whatsapp="+918123456788")
        unpaid = client.post(
            f"/admin/participants/{unpaid_id}/automation/initiate",
            auth=("admin", "Str0ngPass!"),
        )
        assert unpaid.status_code == 409

        with mock.patch.object(main, "send_payment_success_to_n8n", return_value=True) as deliver:
            first = client.post(
                f"/admin/participants/{participant_id}/automation/initiate",
                auth=("admin", "Str0ngPass!"),
            )
            second = client.post(
                f"/admin/participants/{participant_id}/automation/initiate",
                auth=("admin", "Str0ngPass!"),
            )
        assert first.status_code == 200, first.text
        assert first.json()["event_type"] == "workflow.trigger"
        assert first.json()["status"] == "SENT"
        assert second.json()["id"] == first.json()["id"]
        deliver.assert_called_once()
        with test_db() as db:
            assert db.query(models.NotificationOutbox).filter_by(event_type="workflow.trigger").count() == 1
            assert db.query(models.NotificationOutbox).filter_by(event_type="workflow.trigger").one().attempt_count == 1
    finally:
        main.app.dependency_overrides.clear()


def test_admin_schedules_reminder_event_for_automation_workflow(test_db):
    participant_id = add_participant(test_db)
    with test_db() as db:
        participant = db.get(models.Participant, participant_id)
        participant.payment_status = models.PaymentStatus.SUCCESS
        db.add(models.Workshop(
            workshop_name=main.settings.workshop_name,
            slug="reminder-test",
            workshop_date="2099-10-30",
            start_time="09:00",
            end_time="10:00",
            timezone="UTC",
            price_paise=39900,
            max_seats=100,
            registration_status=models.RegistrationStatus.REGISTRATION_OPEN,
            description="Test workshop",
            mode="Online",
            learning_points="[]",
        ))
        db.commit()

    def override_db():
        with test_db() as db:
            yield db

    main.app.dependency_overrides[main.get_db] = override_db
    try:
        with mock.patch.object(main, "send_payment_success_to_n8n", return_value=True) as deliver:
            response = TestClient(main.app).post(
                f"/admin/participants/{participant_id}/reminder/schedule",
                auth=("admin", "Str0ngPass!"),
            )
        assert response.status_code == 200, response.text
        assert response.json()["event_type"] == "reminder.schedule"
        assert response.json()["status"] == "SENT"
        delivered_payload = deliver.call_args.args[0]
        assert delivered_payload["reminder_type"] == "24_hours_before"
        assert delivered_payload["email_template"] == "workshop_reminder"
        assert delivered_payload["scheduled_for"].endswith("+00:00")
    finally:
        main.app.dependency_overrides.clear()


def test_admin_email_draft_is_not_sent_and_requires_verified_payment(test_db):
    participant_id = add_participant(test_db)
    with test_db() as db:
        participant = db.get(models.Participant, participant_id)
        participant.payment_status = models.PaymentStatus.SUCCESS
        db.add(models.Workshop(
            workshop_name=main.settings.workshop_name,
            slug="email-draft-test",
            workshop_date="2099-10-30",
            start_time="09:00",
            end_time="10:00",
            timezone="UTC",
            price_paise=39900,
            max_seats=100,
            registration_status=models.RegistrationStatus.REGISTRATION_OPEN,
            description="Test workshop",
            mode="Online",
            learning_points="[]",
            meeting_url="https://meet.example.test/session",
        ))
        db.commit()

    def override_db():
        with test_db() as db:
            yield db

    main.app.dependency_overrides[main.get_db] = override_db
    try:
        response = TestClient(main.app).post(
            f"/admin/participants/{participant_id}/email-draft?template=workshop_reminder",
            auth=("admin", "Str0ngPass!"),
        )
        assert response.status_code == 200, response.text
        draft = response.json()
        assert draft["to"] == "a@example.com"
        assert draft["sent"] is False
        assert "https://meet.example.test/session" in draft["body"]
        assert "draft only" in draft["note"].lower()
        invalid = TestClient(main.app).post(
            f"/admin/participants/{participant_id}/email-draft?template=unknown",
            auth=("admin", "Str0ngPass!"),
        )
        assert invalid.status_code == 422
        with test_db() as db:
            assert db.query(models.NotificationOutbox).count() == 0
    finally:
        main.app.dependency_overrides.clear()
