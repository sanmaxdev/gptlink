import base64
import json
import time
from pathlib import Path

from gptlink.image_provider import CodexImageProvider


def jwt_with_exp(expires: int, *, plan: str = "plus") -> str:
    header = base64.urlsafe_b64encode(b'{}').decode().rstrip("=")
    payload = base64.urlsafe_b64encode(json.dumps({
        "exp": expires,
        "https://api.openai.com/auth": {"chatgpt_plan_type": plan},
    }).encode()).decode().rstrip("=")
    return f"{header}.{payload}.signature"


def test_payload_requires_image_tool() -> None:
    payload = CodexImageProvider.build_payload(
        prompt="A lighthouse",
        size="1024x1024",
        quality="medium",
        output_format="png",
        background="opaque",
        output_compression=None,
        moderation="auto",
        partial_images=0,
        input_images=[],
        input_image_mask=None,
        action=None,
    )

    assert payload["tools"][0]["type"] == "image_generation"
    assert payload["tools"][0]["model"] == "gpt-image-2"
    assert payload["tool_choice"]["mode"] == "required"


def test_supports_arbitrary_valid_resolutions() -> None:
    assert CodexImageProvider.validate_size("2048x1152") == "2048x1152"
    assert CodexImageProvider.validate_size("3840x2160") == "3840x2160"


def test_rejects_invalid_resolution_constraints() -> None:
    import pytest

    with pytest.raises(ValueError, match="divisible by 16"):
        CodexImageProvider.validate_size("1025x1024")
    with pytest.raises(ValueError, match="Maximum image edge"):
        CodexImageProvider.validate_size("4096x2048")


def test_maps_aspect_ratio_to_valid_size() -> None:
    size = CodexImageProvider.size_from_aspect_ratio("16:9")
    width, height = map(int, size.split("x"))

    assert width % 16 == 0
    assert height % 16 == 0
    assert abs(width / height - 16 / 9) < 0.03


def test_edit_payload_includes_references_mask_and_output_controls() -> None:
    payload = CodexImageProvider.build_payload(
        prompt="Replace the label",
        size="1536x1024",
        quality="high",
        output_format="webp",
        background="auto",
        output_compression=72,
        moderation="low",
        partial_images=2,
        input_images=["data:image/png;base64,AAAA"],
        input_image_mask="data:image/png;base64,BBBB",
        action="edit",
    )
    tool = payload["tools"][0]

    assert tool["action"] == "edit"
    assert tool["input_image_mask"]["image_url"].endswith("BBBB")
    assert tool["output_compression"] == 72
    assert tool["partial_images"] == 2


def test_extracts_final_image_from_nested_event(tmp_path: Path) -> None:
    provider = CodexImageProvider(codex_home=tmp_path, image_dir=tmp_path)
    event = {
        "type": "response.completed",
        "response": {
            "output": [
                {"type": "image_generation_call", "result": "aGVsbG8="}
            ]
        },
    }

    assert provider.extract_image_b64(event) == "aGVsbG8="


def test_sse_parser_preserves_event_type() -> None:
    lines = [
        "event: response.image_generation_call.partial_image",
        'data: {"partial_image_b64":"aGVsbG8="}',
        "",
    ]

    events = list(CodexImageProvider.iter_sse_json(lines))

    assert events[0]["type"] == "response.image_generation_call.partial_image"
    assert events[0]["partial_image_b64"] == "aGVsbG8="


def test_reuses_fresh_hermes_codex_auth_without_copying(tmp_path: Path) -> None:
    codex_home = tmp_path / "codex"
    hermes_home = tmp_path / "hermes"
    hermes_home.mkdir()
    token = jwt_with_exp(int(time.time()) + 3600)
    (hermes_home / "auth.json").write_text(json.dumps({
        "providers": {"openai-codex": {"tokens": {"access_token": token}}}
    }))
    provider = CodexImageProvider(
        codex_home=codex_home, hermes_home=hermes_home, image_dir=tmp_path
    )

    assert provider.auth_source() == "hermes"
    assert provider._read_access_token() == token
    assert not (codex_home / "auth.json").exists()


def test_prefers_codex_cli_auth_over_hermes_auth(tmp_path: Path) -> None:
    codex_home = tmp_path / "codex"
    hermes_home = tmp_path / "hermes"
    codex_home.mkdir()
    hermes_home.mkdir()
    codex_token = jwt_with_exp(int(time.time()) + 3600)
    hermes_token = jwt_with_exp(int(time.time()) + 7200)
    (codex_home / "auth.json").write_text(json.dumps({"tokens": {"access_token": codex_token}}))
    (hermes_home / "auth.json").write_text(json.dumps({
        "providers": {"openai-codex": {"tokens": {"access_token": hermes_token}}}
    }))
    provider = CodexImageProvider(
        codex_home=codex_home, hermes_home=hermes_home, image_dir=tmp_path
    )

    assert provider.auth_source() == "codex_cli"
    assert provider._read_access_token() == codex_token


def test_ignores_expired_hermes_token_and_uses_pool_fallback(tmp_path: Path) -> None:
    hermes_home = tmp_path / "hermes"
    hermes_home.mkdir()
    expired = jwt_with_exp(int(time.time()) - 60)
    pooled = jwt_with_exp(int(time.time()) + 3600)
    (hermes_home / "auth.json").write_text(json.dumps({
        "providers": {"openai-codex": {"tokens": {"access_token": expired}}},
        "credential_pool": {"openai-codex": [{"access_token": pooled, "last_status": "ok"}]},
    }))
    provider = CodexImageProvider(
        codex_home=tmp_path / "codex", hermes_home=hermes_home, image_dir=tmp_path
    )

    assert provider.auth_source() == "hermes"
    assert provider._read_access_token() == pooled
