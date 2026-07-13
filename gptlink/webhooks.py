from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import socket
import time
from urllib.parse import urlparse

import httpx

from gptlink.config import Settings


class WebhookDeliveryError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def validate_webhook_url(value: str, settings: Settings) -> str:
    parsed = urlparse(value.strip())
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("webhook_url must be an absolute HTTPS URL")
    if parsed.username or parsed.password or parsed.fragment:
        raise ValueError("webhook_url cannot contain credentials or a fragment")
    host = parsed.hostname.rstrip(".").lower()
    allowed = set(settings.webhook_allowed_hosts)
    if not allowed or host not in allowed:
        raise ValueError("webhook_url host must be in GPTLINK_WEBHOOK_ALLOWED_HOSTS")
    if parsed.port not in {None, 443} and host not in allowed:
        raise ValueError("Non-standard webhook ports require an explicit host allowlist")
    try:
        addresses = {
            ipaddress.ip_address(item[4][0])
            for item in socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)
        }
    except (OSError, ValueError) as exc:
        raise ValueError("webhook_url host could not be resolved") from exc
    if not addresses:
        raise ValueError("webhook_url host could not be resolved")
    for address in addresses:
        forbidden = (
            address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_reserved
            or address.is_unspecified
        )
        private_allowed = (
            settings.webhook_allow_private and host in allowed and address.is_private
        )
        if forbidden or (not address.is_global and not private_allowed):
            raise ValueError("webhook_url resolves to a blocked network address")
    return parsed.geturl()


def canonical_payload(payload: dict[str, object]) -> bytes:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")


def webhook_headers(
    *, delivery_id: str, event_type: str, payload: bytes, secret: str
) -> dict[str, str]:
    timestamp = str(int(time.time()))
    signature = hmac.new(
        secret.encode("utf-8"), timestamp.encode("ascii") + b"." + payload, hashlib.sha256
    ).hexdigest()
    return {
        "Content-Type": "application/json",
        "User-Agent": "GPTLink-Webhooks/1.0",
        "X-GPTLink-Delivery": delivery_id,
        "X-GPTLink-Event": event_type,
        "X-GPTLink-Timestamp": timestamp,
        "X-GPTLink-Signature": f"v1={signature}",
    }


def deliver_webhook(
    *, url: str, delivery_id: str, event_type: str, payload: dict[str, object], settings: Settings
) -> int:
    if not settings.webhook_secret or len(settings.webhook_secret) < 32:
        raise WebhookDeliveryError(
            "GPTLINK_WEBHOOK_SECRET must contain at least 32 characters"
        )
    safe_url = validate_webhook_url(url, settings)
    body = canonical_payload(payload)
    headers = webhook_headers(
        delivery_id=delivery_id,
        event_type=event_type,
        payload=body,
        secret=settings.webhook_secret,
    )
    with httpx.Client(follow_redirects=False, trust_env=False, timeout=10.0) as client:
        response = client.post(safe_url, content=body, headers=headers)
    if not 200 <= response.status_code < 300:
        raise WebhookDeliveryError(
            f"Webhook endpoint returned HTTP {response.status_code}", response.status_code
        )
    return response.status_code
