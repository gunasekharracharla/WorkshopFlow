"""Tests for international WhatsApp validation and duplicate-registration handling.

Run from the backend folder:  python -m unittest test_registration -v
(The HTTP tests need `pip install httpx`; they are skipped if it is missing.)
Tests use a temporary SQLite database and a fake Razorpay order - nothing real is touched.
"""

import os
import pathlib
import sys
import tempfile
import unittest

BACKEND_DIR = pathlib.Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault("RAZORPAY_KEY_ID", "rzp_test_placeholder")
os.environ.setdefault("RAZORPAY_KEY_SECRET", "placeholder_secret")

import schemas  # noqa: E402

try:
    from fastapi.testclient import TestClient  # noqa: E402
except Exception:  # httpx missing
    TestClient = None


class WhatsappValidationTests(unittest.TestCase):
    def test_valid_numbers_are_normalized_to_e164(self):
        cases = {
            "8123456789": "+918123456789",          # India, no country code (legacy input)
            "08123456789": "+918123456789",
            "+91 81234 56789": "+918123456789",
            "91-8123456789": "+918123456789",
            "+1 415 555 2671": "+14155552671",      # United States
            "+44 7911 123456": "+447911123456",     # United Kingdom
            "+971 50 123 4567": "+971501234567",    # UAE
            "+61 412 345 678": "+61412345678",      # Australia
            "+1 506 234 5678": "+15062345678",      # Canada
            "+65 8123 4567": "+6581234567",         # Singapore
            "+49 1512 3456789": "+4915123456789",   # Germany
            "+33 6 12 34 56 78": "+33612345678",    # France
            "+81 80 3141 5926": "+818031415926",    # Japan
            "0091 8123456789": "+918123456789",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(schemas.normalize_whatsapp(raw), expected)

    def test_invalid_numbers_are_rejected(self):
        bad = [
            "", "abc", "12345", "81234567",              # empty / short
            "812345678912345",                            # too long
            "+91 5123456789",                             # India must start 6-9
            "+1 123 456 7890",                            # invalid US area code
            "+44 12",                                     # UK too short
            "+999 1234567",                               # unknown country code
            "+91 1800 123 4567",
        ]
        for raw in bad:
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    schemas.normalize_whatsapp(raw)

    def test_artificial_numbers_are_rejected(self):
        bad = ["1234567890", "0123456789", "9876543210", "0987654321"]
        bad += [str(d) * 10 for d in range(10)]
        bad += ["+91 9999999999", "+91 9876543210", "+44 7777777777", "+1 2222222222"]
        for raw in bad:
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    schemas.normalize_whatsapp(raw)

    def test_repeated_digits_inside_a_real_number_are_fine(self):
        self.assertEqual(schemas.normalize_whatsapp("9911223344"), "+919911223344")
        self.assertEqual(schemas.normalize_whatsapp("+91 88888 12345"), "+918888812345")

    def test_lookup_values_include_legacy_indian_format(self):
        self.assertEqual(schemas.whatsapp_lookup_values("+918123456789"), ["+918123456789", "8123456789"])
        self.assertEqual(schemas.whatsapp_lookup_values("+14155552671"), ["+14155552671"])


@unittest.skipIf(TestClient is None, "httpx is not installed")
class RegistrationDuplicateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        import main
        import models

        cls.main, cls.models = main, models
        cls.tmpdir = tempfile.TemporaryDirectory()
        cls.engine = create_engine(f"sqlite:///{cls.tmpdir.name}/test.db", connect_args={"check_same_thread": False})
        models.Base.metadata.create_all(bind=cls.engine)
        cls.Session = sessionmaker(bind=cls.engine, autocommit=False, autoflush=False)

        def override_db():
            db = cls.Session()
            try:
                yield db
            finally:
                db.close()

        main.app.dependency_overrides[main.get_db] = override_db
        cls.original_order = main.create_razorpay_order
        cls.order_calls = []

        def fake_order(amount, receipt):
            cls.order_calls.append(receipt)
            return {"id": f"order_test_{len(cls.order_calls)}"}

        main.create_razorpay_order = fake_order
        cls.client = TestClient(main.app)

    @classmethod
    def tearDownClass(cls):
        cls.main.app.dependency_overrides.clear()
        cls.main.create_razorpay_order = cls.original_order
        cls.engine.dispose()
        cls.tmpdir.cleanup()

    def payload(self, **overrides):
        data = {
            "name": "Test User", "email": "test@example.com", "whatsapp": "+918123456789",
            "role": "Full-Stack Developer", "experience": "3", "workshop": schemas.WORKSHOP_NAME,
        }
        data.update(overrides)
        return data

    def mark_paid(self, participant_id):
        with self.Session() as db:
            row = db.query(self.models.Participant).get(participant_id)
            row.payment_status = self.models.PaymentStatus.SUCCESS
            db.commit()

    def test_flow(self):
        c = self.client
        # new registration -> stored as E.164, price is server side
        r = c.post("/register", json=self.payload(email="  New.User@Example.COM ", whatsapp="+1 415 555 2671"))
        self.assertEqual(r.status_code, 201, r.text)
        first_id = r.json()["id"]
        payment_token = r.json()["payment_token"]
        with self.Session() as db:
            row = db.query(self.models.Participant).get(first_id)
            self.assertEqual(row.email, "new.user@example.com")
            self.assertEqual(row.whatsapp, "+14155552671")

        # unpaid duplicate resumes the SAME registration (no second record)
        r = c.post("/register", json=self.payload(email="NEW.USER@example.com", whatsapp="+1 415 555 2671"))
        self.assertEqual(r.json()["id"], first_id)
        with self.Session() as db:
            self.assertEqual(db.query(self.models.Participant).count(), 1)

        # payment order can be created for the pending registration
        r = c.post("/payment/create", json={"participant_id": first_id, "payment_token": payment_token})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(len(self.order_calls), 1)

        # once paid, the same email (any case / spaces) is blocked and no order is created
        self.mark_paid(first_id)
        r = c.post("/register", json=self.payload(email=" NEW.USER@EXAMPLE.COM ", whatsapp="+44 7911 123456"))
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()["detail"], "This email address is already registered for this workshop")
        self.assertEqual(len(self.order_calls), 1)
        r = c.post("/payment/create", json={"participant_id": first_id, "payment_token": payment_token})
        self.assertEqual(r.status_code, 409)

        # same WhatsApp number, different email -> WhatsApp message
        r = c.post("/register", json=self.payload(email="other@example.com", whatsapp="+14155552671"))
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()["detail"], "This WhatsApp number is already registered for this workshop")

        # legacy row stored as bare 10 digits is matched by the new E.164 format
        with self.Session() as db:
            db.add(self.models.Participant(
                name="Legacy", email="legacy@example.com", whatsapp="9123456780", role="Other",
                experience="1", workshop=schemas.WORKSHOP_NAME, amount_paise=39900,
                payment_status=self.models.PaymentStatus.SUCCESS))
            db.commit()
        r = c.post("/register", json=self.payload(email="fresh@example.com", whatsapp="+91 91234 56780"))
        self.assertEqual(r.status_code, 409)
        self.assertIn("WhatsApp number is already registered", r.json()["detail"])

    def test_invalid_whatsapp_gives_422_on_whatsapp_field(self):
        r = self.client.post("/register", json=self.payload(email="bad@example.com", whatsapp="9876543210"))
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.json()["detail"][0]["loc"][-1], "whatsapp")


if __name__ == "__main__":
    unittest.main()
