import hashlib
import hmac
from pathlib import Path

import pytest

from gptlink.config import Settings
from gptlink.webhooks import canonical_payload, validate_webhook_url, webhook_headers


def webhook_settings(tmp_path: Path, **overrides) -> Settings:
    values = {
        "root_dir": tmp_path,
        "data_dir": tmp_path / "data",
        "image_dir": tmp_path / "data" / "images",
        "database_path": tmp_path / "data" / "gptlink.db",
        "codex_home": tmp_path / "codex",
        "hermes_home": tmp_path / "hermes",
        "host": "127.0.0.1",
        "port": 8787,
        "public_base_url": "http://127.0.0.1:8787",
        "mcp_allowed_roots": (),
        "webhook_secret": "s" * 32,
    }
    values.update(overrides)
    return Settings(**values)


def test_webhook_url_blocks_private_networks(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "gptlink.webhooks.socket.getaddrinfo",
        lambda *_args, **_kwargs: [(None, None, None, None, ("127.0.0.1", 443))],
    )

    with pytest.raises(ValueError, match="blocked network"):
        validate_webhook_url(
            "https://callback.example/path",
            webhook_settings(tmp_path, webhook_allowed_hosts=("callback.example",)),
        )


def test_webhook_url_allows_resolved_public_https(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "gptlink.webhooks.socket.getaddrinfo",
        lambda *_args, **_kwargs: [(None, None, None, None, ("93.184.216.34", 443))],
    )

    assert (
        validate_webhook_url(
            "https://callback.example/path",
            webhook_settings(tmp_path, webhook_allowed_hosts=("callback.example",)),
        )
        == "https://callback.example/path"
    )


def test_webhook_url_requires_operator_allowlist(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "gptlink.webhooks.socket.getaddrinfo",
        lambda *_args, **_kwargs: [(None, None, None, None, ("93.184.216.34", 443))],
    )

    with pytest.raises(ValueError, match="must be in"):
        validate_webhook_url("https://callback.example/path", webhook_settings(tmp_path))


def test_webhook_signature_covers_timestamp_and_canonical_body(monkeypatch) -> None:
    monkeypatch.setattr("gptlink.webhooks.time.time", lambda: 1234567890)
    secret = "x" * 32
    body = canonical_payload({"type": "image_job.completed", "id": "evt_test"})
    headers = webhook_headers(
        delivery_id="whd_test",
        event_type="image_job.completed",
        payload=body,
        secret=secret,
    )
    expected = hmac.new(
        secret.encode(), b"1234567890." + body, hashlib.sha256
    ).hexdigest()

    assert headers["X-GPTLink-Signature"] == f"v1={expected}"
