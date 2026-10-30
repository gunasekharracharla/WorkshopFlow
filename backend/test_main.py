import pathlib
import sys
import unittest
from dataclasses import replace
from unittest import mock

BACKEND_DIR = pathlib.Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


class AppStartupTests(unittest.TestCase):
    def test_app_initializes_without_frontend_directory(self):
        import main

        self.assertIsNotNone(main.app)

    def test_public_config_exposes_only_white_label_branding(self):
        from fastapi.testclient import TestClient

        import main

        response = TestClient(main.app).get("/public-config")

        self.assertEqual(response.status_code, 200)
        config = response.json()
        self.assertEqual(
            set(config),
            {
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
            },
        )
        self.assertNotIn("RAZORPAY_KEY_SECRET", config)

    def test_product_and_attendee_pages_have_distinct_routes(self):
        from fastapi.testclient import TestClient

        import main

        client = TestClient(main.app)
        product_page = client.get("/")
        attendee_page = client.get("/events/full-stack-web-development")

        self.assertEqual(product_page.status_code, 200)
        self.assertIn("Turn your expertise into a", product_page.text)
        self.assertEqual(attendee_page.status_code, 200)
        self.assertIn('id="registrationForm"', attendee_page.text)
        self.assertIn("This site does not send confirmation emails.", attendee_page.text)
        self.assertNotIn('id="registrationForm"', product_page.text)

    def test_public_config_includes_only_configured_policy_links(self):
        from fastapi.testclient import TestClient

        import main

        with mock.patch.object(
            main,
            "settings",
            replace(
                main.settings,
                privacy_policy_url="https://workshop.example/privacy",
                registration_terms_url="https://workshop.example/terms",
            ),
        ):
            response = TestClient(main.app).get("/public-config")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["privacy_policy_url"], "https://workshop.example/privacy")
        self.assertEqual(response.json()["registration_terms_url"], "https://workshop.example/terms")
        self.assertNotIn("secret", response.text.lower())


if __name__ == "__main__":
    unittest.main()
