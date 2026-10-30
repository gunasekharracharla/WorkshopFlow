"""
payment.py
----------
Everything related to Razorpay lives here:

- create_razorpay_order()       -> creates a TEST MODE order
- verify_razorpay_signature()   -> verifies a payment signature on the backend
- send_payment_success_to_n8n() -> (future) notifies an n8n workflow

No other file talks to Razorpay directly. This keeps payment logic in one
place and makes it easy to audit.
"""

import hashlib
import hmac
import logging
import os

import razorpay
import requests
from dotenv import load_dotenv

load_dotenv()

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "").strip()
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "").strip()
RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET", "").strip()
AUTOMATION_WEBHOOK_URL = os.getenv(
    "AUTOMATION_WEBHOOK_URL",
    os.getenv("N8N_WEBHOOK_URL", ""),
).strip()
N8N_WEBHOOK_URL = AUTOMATION_WEBHOOK_URL
logger = logging.getLogger("workshop.automation")

if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
    raise RuntimeError(
        "RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET must be set in your .env file. "
        "Copy .env.example to .env and fill in your Razorpay TEST MODE keys."
    )

razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))


def create_razorpay_order(amount_paise: int, receipt: str) -> dict:
    """
    Creates a Razorpay order in TEST MODE and returns the raw order dict
    from Razorpay (contains at least an "id" field).

    Razorpay always expects amounts in the smallest currency unit
    (paise for INR), so we multiply rupees by 100.
    """
    order_data = {
        "amount": int(amount_paise),
        "currency": "INR",
        "receipt": receipt,
        "payment_capture": 1,  # auto-capture the payment once authorized
    }

    try:
        order = razorpay_client.order.create(data=order_data)
    except Exception as exc:
        # Any Razorpay SDK/network error gets converted into a clean error
        # that main.py can turn into an HTTP 502 response.
        raise RuntimeError(f"Failed to create Razorpay order: {exc}") from exc

    return order


def fetch_razorpay_payment(payment_id: str) -> dict:
    try:
        return razorpay_client.payment.fetch(payment_id)
    except Exception as exc:
        raise RuntimeError("Failed to fetch Razorpay payment") from exc


def fetch_razorpay_order(order_id: str) -> dict:
    try:
        return razorpay_client.order.fetch(order_id)
    except Exception as exc:
        raise RuntimeError("Failed to fetch Razorpay order") from exc


def verify_razorpay_signature(
    razorpay_order_id: str,
    razorpay_payment_id: str,
    razorpay_signature: str,
) -> bool:
    """Verify a Razorpay Checkout signature using order_id|payment_id and HMAC-SHA256."""
    if not razorpay_order_id or not razorpay_payment_id or not razorpay_signature:
        return False
    message = f"{razorpay_order_id}|{razorpay_payment_id}"
    generated_signature = hmac.new(
        key=RAZORPAY_KEY_SECRET.encode("utf-8"),
        msg=message.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(generated_signature, razorpay_signature)


def verify_razorpay_webhook_signature(body: bytes, signature: str) -> bool:
    if not body or not signature:
        return False
    generated_signature = hmac.new(
        key=RAZORPAY_WEBHOOK_SECRET.encode("utf-8"),
        msg=body,
        digestmod=hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(generated_signature, signature or "")


def send_payment_success_to_n8n(payload: dict) -> bool:
    """
    Sends successful registration/payment data to an n8n webhook, if one is
    configured.

    IMPORTANT: This function must NEVER raise an exception that could break
    the payment verification flow. If n8n is not configured, unreachable,
    or returns an error, we simply log it and move on.
    """
    if not AUTOMATION_WEBHOOK_URL:
        return False

    try:
        response = requests.post(
            AUTOMATION_WEBHOOK_URL,
            json=payload,
            headers={"X-Idempotency-Key": str(payload.get("idempotency_key", ""))},
            timeout=10,
        )
        return response.ok
    except Exception as exc:
        logger.warning(
            "Automation webhook delivery failed for participant %s: %s",
            payload.get("participant_id"),
            type(exc).__name__,
        )
        return False
