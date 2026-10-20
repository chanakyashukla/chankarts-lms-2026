"""
Razorpay server-side integration.

Status: structure complete and unit-testable with test credentials.
Live behaviour is UNVERIFIED until RAZORPAY_MODE=test|live credentials and a
webhook secret are configured — the code never pretends otherwise.

Secrets (key id/secret, webhook secret) are read from environment variables
only and are never returned to the browser or written to logs.
"""
import hashlib
import hmac
import logging
import base64
from typing import Optional

import httpx

from app.config import get_settings

logger = logging.getLogger("chankarts.payments")


class PaymentGatewayError(Exception):
    pass


class RazorpayService:
    API_BASE = "https://api.razorpay.com/v1"

    @property
    def mode(self) -> str:
        return get_settings().RAZORPAY_MODE.lower()

    @property
    def enabled(self) -> bool:
        return self.mode in ("test", "live")

    def _auth(self) -> tuple[str, str]:
        settings = get_settings()
        if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
            raise PaymentGatewayError("Razorpay credentials are not configured")
        return settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET

    @property
    def key_id(self) -> str:
        return get_settings().RAZORPAY_KEY_ID

    def public_config(self) -> dict:
        """Safe subset for the frontend checkout."""
        return {
            "enabled": self.enabled,
            "mode": self.mode if self.enabled else "disabled",
            "key_id": self.key_id if self.enabled else None,
            "currency": get_settings().RAZORPAY_CURRENCY or "INR",
        }

    def create_order(self, *, amount_paise: int, receipt: str, notes: Optional[dict] = None) -> dict:
        if not self.enabled:
            raise PaymentGatewayError("Online payments are not enabled for this academy yet")
        if amount_paise <= 0:
            raise PaymentGatewayError("Amount must be positive")

        payload = {
            "amount": amount_paise,
            "currency": get_settings().RAZORPAY_CURRENCY or "INR",
            "receipt": receipt[:40],
            "notes": notes or {},
        }
        try:
            response = httpx.post(
                f"{self.API_BASE}/orders",
                json=payload,
                auth=self._auth(),
                timeout=20.0,
            )
        except httpx.HTTPError as exc:
            logger.warning("Razorpay order request failed: %s", exc)
            raise PaymentGatewayError("Could not reach the payment provider") from exc

        if response.status_code >= 400:
            logger.warning("Razorpay order failed: %s", response.status_code)
            raise PaymentGatewayError("The payment provider rejected the order request")

        data = response.json()
        return {
            "order_id": data["id"],
            "amount": int(data["amount"]),
            "currency": data.get("currency", "INR"),
            "status": data.get("status", "created"),
            "key_id": self.key_id,
        }

    def fetch_payment(self, payment_id: str) -> dict:
        if not self.enabled:
            raise PaymentGatewayError("Online payments are not enabled")
        response = httpx.get(
            f"{self.API_BASE}/payments/{payment_id}",
            auth=self._auth(),
            timeout=20.0,
        )
        if response.status_code >= 400:
            raise PaymentGatewayError("Could not fetch payment from provider")
        return response.json()

    # ------------------------------------------------------------------
    # Signature verification (constant-time comparisons)
    # ------------------------------------------------------------------
    def verify_payment_signature(self, *, order_id: str, payment_id: str, signature: str) -> bool:
        """HMAC-SHA256(order_id|payment_id, key_secret)."""
        settings = get_settings()
        if not settings.RAZORPAY_KEY_SECRET or not signature:
            return False
        expected = hmac.new(
            settings.RAZORPAY_KEY_SECRET.encode(),
            f"{order_id}|{payment_id}".encode(),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature.strip().lower())

    def verify_webhook_signature(self, *, raw_body: bytes, signature: str) -> bool:
        """HMAC-SHA256(raw_request_body, webhook_secret) — raw bytes, never re-serialised."""
        settings = get_settings()
        if not settings.RAZORPAY_WEBHOOK_SECRET or not signature:
            return False
        expected = hmac.new(
            settings.RAZORPAY_WEBHOOK_SECRET.encode(),
            raw_body,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature.strip().lower())


razorpay_service = RazorpayService()
