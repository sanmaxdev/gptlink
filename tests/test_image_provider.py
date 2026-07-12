from pathlib import Path

from gptlink.image_provider import CodexImageProvider


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
