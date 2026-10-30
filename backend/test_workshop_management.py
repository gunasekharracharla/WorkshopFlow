import pathlib
import sys
import tempfile
import os
from unittest import mock

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = pathlib.Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("RAZORPAY_KEY_ID", "rzp_test_placeholder")
os.environ.setdefault("RAZORPAY_KEY_SECRET", "placeholder_secret")
os.environ.setdefault("ADMIN_USERNAME", "admin")
os.environ.setdefault("ADMIN_PASSWORD", "Str0ngPass!")

import main
import models


def make_session():
    tmpdir = tempfile.TemporaryDirectory()
    engine = create_engine(f"sqlite:///{tmpdir.name}/test.db", connect_args={"check_same_thread": False})
    models.Base.metadata.create_all(bind=engine)
    return tmpdir, engine, sessionmaker(bind=engine, autocommit=False, autoflush=False)


def test_admin_workshop_update_public_fields_private_meeting_and_history():
    tmpdir, engine, Session = make_session()
    original = main.app.dependency_overrides.get(main.get_db)

    def override_db():
        with Session() as db:
            yield db

    main.app.dependency_overrides[main.get_db] = override_db
    try:
        client = TestClient(main.app)
        assert client.get("/admin/workshop").status_code == 401
        payload = {
            "workshop_name": "Full-Stack Web Development Workshop October",
            "slug": "full-stack-web-development-october",
            "workshop_date": "2026-10-17",
            "start_time": "17:00",
            "end_time": "18:00",
            "timezone": "Asia/Kolkata",
            "price_paise": 49900,
            "max_seats": 80,
            "registration_status": "REGISTRATION_OPEN",
            "description": "Updated workshop",
            "mode": "Online Live Session",
            "learning_points": ["Practical AI", "Reusable prompts"],
            "meeting_platform": "Google Meet",
            "meeting_id": "abc-defg-hij",
            "meeting_url": "https://meet.google.com/abc-defg-hij",
        }
        response = client.put("/admin/workshop", json=payload, auth=("admin", "Str0ngPass!"))
        assert response.status_code == 200, response.text
        public = client.get("/workshop")
        assert public.status_code == 200
        public_data = public.json()
        assert public_data["name"] == payload["workshop_name"]
        assert public_data["price"] == 499
        assert public_data["registration_status"] == "REGISTRATION_OPEN"
        assert "meeting_url" not in public_data
        registration = client.post("/register", json={
            "name": "New Workshop Attendee",
            "email": "new-attendee@example.com",
            "whatsapp": "8123456789",
            "role": "Full-Stack Developer",
            "experience": "1",
            "workshop": payload["workshop_name"],
        })
        assert registration.status_code == 201, registration.text
        with Session() as db:
            attendee = db.get(models.Participant, registration.json()["id"])
            assert attendee.workshop == payload["workshop_name"]
        admin_data = client.get("/admin/workshop", auth=("admin", "Str0ngPass!")).json()
        assert admin_data["meeting_url"] == payload["meeting_url"]
        history = client.get("/admin/workshop/history", auth=("admin", "Str0ngPass!")).json()
        assert len(history) == 1
        assert history[0]["new_values"]["price_paise"] == 49900
    finally:
        main.app.dependency_overrides.clear()
        if original:
            main.app.dependency_overrides[main.get_db] = original
        engine.dispose()
        tmpdir.cleanup()


def test_invalid_workshop_configuration_is_rejected():
    from schemas import WorkshopAdminUpdate
    import pytest

    with pytest.raises(ValueError):
        WorkshopAdminUpdate(
            workshop_name="Workshop",
            slug="bad slug",
            workshop_date="2026-10-17",
            start_time="17:00",
            end_time="18:00",
            timezone="Asia/Kolkata",
            price_paise=-1,
            max_seats=0,
            registration_status="REGISTRATION_OPEN",
        )


def test_closed_registration_rejects_new_registration():
    tmpdir, engine, Session = make_session()
    original = main.app.dependency_overrides.get(main.get_db)

    def override_db():
        with Session() as db:
            yield db

    main.app.dependency_overrides[main.get_db] = override_db
    try:
        with Session() as db:
            workshop = main.get_workshop(db)
            workshop.registration_status = models.RegistrationStatus.REGISTRATION_CLOSED
            db.commit()
        response = TestClient(main.app).post("/register", json={
            "name": "Closed User",
            "email": "closed@example.com",
            "whatsapp": "8123456789",
            "role": "Full-Stack Developer",
            "experience": "2",
            "workshop": main.settings.workshop_name,
        })
        assert response.status_code == 409
    finally:
        main.app.dependency_overrides.clear()
        if original:
            main.app.dependency_overrides[main.get_db] = original
        engine.dispose()
        tmpdir.cleanup()


def test_new_payment_order_uses_database_price_and_old_attempt_keeps_snapshot():
    tmpdir, engine, Session = make_session()
    original = main.app.dependency_overrides.get(main.get_db)

    def override_db():
        with Session() as db:
            yield db

    main.app.dependency_overrides[main.get_db] = override_db
    try:
        with Session() as db:
            workshop = main.get_workshop(db)
            workshop.price_paise = 49900
            participant = models.Participant(
                name="Price User",
                email="price@example.com",
                whatsapp="+918123456789",
                role="Full-Stack Developer",
                experience="2",
                workshop=workshop.workshop_name,
                amount_paise=39900,
                payment_status=models.PaymentStatus.PENDING,
                payment_token_hash=main.token_hash("price-token"),
            )
            db.add(participant)
            db.commit()
            db.refresh(participant)
            db.add(models.PaymentAttempt(participant_id=participant.id, razorpay_order_id="old-order", amount_paise=39900, status=models.PaymentStatus.PENDING))
            db.commit()
            participant_id = participant.id
        with mock.patch.object(main, "create_razorpay_order", return_value={"id": "new-order"}) as create_order:
            response = TestClient(main.app).post("/payment/create", json={"participant_id": participant_id, "payment_token": "price-token"})
        assert response.status_code == 200, response.text
        create_order.assert_called_once_with(39900, f"participant_{participant_id}")
        with Session() as db:
            attempts = db.query(models.PaymentAttempt).order_by(models.PaymentAttempt.id).all()
            assert attempts[0].amount_paise == 39900
            assert attempts[1].amount_paise == 39900
    finally:
        main.app.dependency_overrides.clear()
        if original:
            main.app.dependency_overrides[main.get_db] = original
        engine.dispose()
        tmpdir.cleanup()


def test_admin_summary_contains_role_breakdown_and_csv_export():
    tmpdir, engine, Session = make_session()
    original = main.app.dependency_overrides.get(main.get_db)

    def override_db():
        with Session() as db:
            yield db

    main.app.dependency_overrides[main.get_db] = override_db
    try:
        with Session() as db:
            workshop = main.get_workshop(db)
            db.add_all([
                models.Participant(
                    name="Alpha",
                    email="alpha@example.com",
                    whatsapp="+918123456700",
                    role="Full-Stack Developer",
                    experience="2",
                    workshop=workshop.workshop_name,
                    amount_paise=39900,
                    payment_status=models.PaymentStatus.SUCCESS,
                ),
                models.Participant(
                    name="Beta",
                    email="beta@example.com",
                    whatsapp="+918123456701",
                    role="Student/Fresher",
                    experience="0",
                    workshop=workshop.workshop_name,
                    amount_paise=39900,
                    payment_status=models.PaymentStatus.PENDING,
                ),
            ])
            db.commit()

        client = TestClient(main.app)
        summary = client.get("/admin/summary", auth=("admin", "Str0ngPass!"))
        assert summary.status_code == 200, summary.text
        summary_payload = summary.json()
        assert summary_payload["role_breakdown"]["Full-Stack Developer"] == 1
        assert summary_payload["role_breakdown"]["Student/Fresher"] == 1

        export = client.get("/admin/participants/export", auth=("admin", "Str0ngPass!"))
        assert export.status_code == 200, export.text
        assert export.headers["content-type"].startswith("text/csv")
        body = export.text
        assert "name,email,whatsapp" in body
        assert "Full-Stack Developer" in body
        assert "Student/Fresher" in body
    finally:
        main.app.dependency_overrides.clear()
        if original:
            main.app.dependency_overrides[main.get_db] = original
        engine.dispose()
        tmpdir.cleanup()
