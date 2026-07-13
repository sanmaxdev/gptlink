import asyncio
from pathlib import Path

import httpx

import gptlink.main as main
from gptlink.image_provider import GeneratedImage


def generated_image(tmp_path: Path, index: int = 0) -> GeneratedImage:
    return GeneratedImage(
        id=f"img_test_{index}",
        path=tmp_path / f"image-{index}.png",
        base64_data="aGVsbG8=",
        model="gpt-image-2",
        quality="high",
        size="1024x1024",
        output_format="png",
        background="opaque",
        usage={"total_tokens": 1},
    )


def install_api_stubs(monkeypatch, tmp_path: Path) -> list[dict]:
    calls: list[dict] = []

    async def refresh_auth() -> dict:
        return {"account": {"source": "test"}}

    async def generate_many(*, count: int, **kwargs):
        calls.append({"count": count, **kwargs})
        return [generated_image(tmp_path, index) for index in range(count)]

    monkeypatch.setattr(main.database, "validate_api_key", lambda _: True)
    monkeypatch.setattr(main.database, "record_image", lambda **_: None)
    monkeypatch.setattr(main, "refresh_codex_auth", refresh_auth)
    monkeypatch.setattr(main, "generate_many", generate_many)
    return calls


def request(method: str, path: str, **kwargs) -> httpx.Response:
    async def send() -> httpx.Response:
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(send())


def test_models_require_gateway_key(monkeypatch) -> None:
    monkeypatch.setattr(main.database, "validate_api_key", lambda _: False)

    response = request("GET", "/v1/models")

    assert response.status_code == 401
    assert response.json()["error"]["type"] == "authentication_error"


def test_image_generation_contract(monkeypatch, tmp_path: Path) -> None:
    calls = install_api_stubs(monkeypatch, tmp_path)

    response = request(
        "POST",
        "/v1/images/generations",
        headers={"Authorization": "Bearer gptlink_test_secret"},
        json={
            "model": "gpt-image-2",
            "prompt": "A clean product image",
            "size": "1024x1024",
            "quality": "high",
            "n": 2,
            "response_format": "b64_json",
        },
    )

    assert response.status_code == 200
    assert len(response.json()["data"]) == 2
    assert response.json()["data"][0]["b64_json"] == "aGVsbG8="
    assert calls[0]["count"] == 2
    assert calls[0]["quality"] == "high"


def test_multipart_edit_contract(monkeypatch, tmp_path: Path) -> None:
    calls = install_api_stubs(monkeypatch, tmp_path)

    response = request(
        "POST",
        "/v1/images/edits",
        headers={"Authorization": "Bearer gptlink_test_secret"},
        data={"prompt": "Replace only the background", "response_format": "b64_json"},
        files=[
            ("image", ("reference.png", b"reference", "image/png")),
            ("mask", ("mask.png", b"mask", "image/png")),
        ],
    )

    assert response.status_code == 200
    assert response.json()["data"][0]["b64_json"] == "aGVsbG8="
    assert calls[0]["input_images"][0].startswith("data:image/png;base64,")
    assert calls[0]["input_image_mask"].startswith("data:image/png;base64,")
