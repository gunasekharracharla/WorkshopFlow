import hashlib
import hmac
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

BACKEND_DIR = pathlib.Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("RAZORPAY_KEY_ID", "rzp_test_placeholder")
os.environ.setdefault("RAZORPAY_KEY_SECRET", "placeholder_secret")
os.environ.setdefault("ADMIN_USERNAME", "admin")
os.environ.setdefault("ADMIN_PASSWORD", "Str0ngPass!")
os.environ.setdefault("N8N_WEBHOOK_URL", "https://example.com/hook")

from fastapi.testclient import TestClient
import main
import models


class SecurityHardeningTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        self.engine = create_engine(f"sqlite:///{self.tmpdir.name}/test.db", connect_args={"check_same_thread": False})
        self.Session = sessionmaker(bind=self.engine, autocommit=False, autoflush=False)

    def tearDown(self):
        if hasattr(self, "engine"):
            self.engine.dispose()
        self.tmpdir.cleanup()

    def test_verify_razorpay_signature_rejects_invalid_signature(self):
        valid = main.verify_razorpay_signature("order_123", "pay_456", self._signature("order_123", "pay_456"))
        self.assertTrue(valid)
        self.assertFalse(main.verify_razorpay_signature("order_123", "pay_456", "bad_signature"))

    def test_payment_verification_triggers_n8n_after_success(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            from sqlalchemy import create_engine
            from sqlalchemy.orm import sessionmaker

            engine = create_engine(f"sqlite:///{tmpdir}/test.db", connect_args={"check_same_thread": False})
            try:
                models.Base.metadata.create_all(bind=engine)
                Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)

                def override_db():
                    db = Session()
                    try:
                        yield db
                    finally:
                        db.close()

                main.app.dependency_overrides[main.get_db] = override_db
                participant = models.Participant(
                    name="Test User",
                    email="test@example.com",
                    whatsapp="+919876543210",
                    role="Full-Stack Developer",
                    experience="2",
                    workshop=main.settings.workshop_name,
                    amount_paise=main.settings.workshop_price * 100,
                    payment_status=models.PaymentStatus.PENDING,
                    razorpay_order_id="order_123",
                    payment_token_hash="token-hash",
                )
                with Session() as db:
                    db.add(participant)
                    db.commit()
                    db.refresh(participant)
                    db.add(models.PaymentAttempt(
                        participant_id=participant.id,
                        razorpay_order_id="order_123",
                        amount_paise=main.settings.workshop_price * 100,
                        status=models.PaymentStatus.PENDING,
                    ))
                    db.commit()

                signature = self._signature("order_123", "pay_456")
                provider_order = {"id": "order_123", "amount": main.settings.workshop_price * 100, "currency": "INR"}
                provider_payment = {"id": "pay_456", "order_id": "order_123", "amount": main.settings.workshop_price * 100, "currency": "INR", "status": "captured"}
                with mock.patch.object(main, "fetch_razorpay_order", return_value=provider_order), mock.patch.object(main, "fetch_razorpay_payment", return_value=provider_payment), mock.patch.object(main, "send_payment_success_to_n8n", return_value=True) as n8n_mock:
                    response = TestClient(main.app).post(
                        "/payment/verify",
                        json={"razorpay_order_id": "order_123", "razorpay_payment_id": "pay_456", "razorpay_signature": signature},
                    )
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertTrue(response.json()["success"])
                    n8n_mock.assert_called_once()
            finally:
                main.app.dependency_overrides.clear()
                engine.dispose()

    def test_webhook_invalid_signature_rejected(self):
        client = TestClient(main.app)
        payload = {"event": "payment.captured", "payload": {"payment": {"entity": {"id": "pay_456", "order_id": "order_123"}}}}
        response = client.post("/payment/webhook", data='{"event":"payment.captured"}', headers={"X-Razorpay-Signature": "bad"})
        self.assertEqual(response.status_code, 400)

    def _signature(self, order_id: str, payment_id: str) -> str:
        message = f"{order_id}|{payment_id}"
        return hmac.new(
            os.environ["RAZORPAY_KEY_SECRET"].encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()


if __name__ == "__main__":
    unittest.main()
