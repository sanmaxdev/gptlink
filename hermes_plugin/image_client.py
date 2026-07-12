#!/usr/bin/env python3
"""Generate or edit images through the plugin-managed GPTLink service."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import pathlib
import urllib.error
import urllib.request
import uuid


def managed_config() -> dict:
    path = pathlib.Path(os.environ.get(
        "GPTLINK_CONFIG_FILE", pathlib.Path.home() / ".config/gptlink/hermes.json"
    ))
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def request(url: str, key: str, data: bytes, content_type: str) -> dict:
    req = urllib.request.Request(url, data=data, method="POST", headers={
        "Authorization": f"Bearer {key}", "Content-Type": content_type,
    })
    try:
        with urllib.request.urlopen(req, timeout=360) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"GPTLink returned HTTP {exc.code}: {detail}") from exc


def multipart(fields: dict[str, str], images: list[pathlib.Path]) -> tuple[bytes, str]:
    boundary = f"----gptlink{uuid.uuid4().hex}"
    body = bytearray()
    for name, value in fields.items():
        body.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode())
    for image in images:
        mime = mimetypes.guess_type(image.name)[0] or "application/octet-stream"
        body.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{image.name}\"\r\nContent-Type: {mime}\r\n\r\n".encode())
        body.extend(image.read_bytes())
        body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode())
    return bytes(body), f"multipart/form-data; boundary={boundary}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate or edit an image with GPTLink")
    parser.add_argument("prompt")
    parser.add_argument("--reference", action="append", default=[])
    parser.add_argument("--aspect-ratio", default="1:1")
    parser.add_argument("--quality", choices=["auto", "low", "medium", "high"], default="auto")
    parser.add_argument("--format", choices=["png", "jpeg", "webp"], default="png")
    parser.add_argument("--output", default="gptlink-output.png")
    args = parser.parse_args()

    config = managed_config()
    base_url = os.environ.get("GPTLINK_BASE_URL", str(config.get("base_url", ""))).rstrip("/")
    key = os.environ.get("GPTLINK_API_KEY", str(config.get("api_key", "")))
    if not base_url or not key:
        raise SystemExit("GPTLink is not configured. Run gptlink_operator.py setup first")

    references = [pathlib.Path(path).expanduser().resolve() for path in args.reference]
    if any(not path.is_file() for path in references):
        raise SystemExit("A reference image does not exist")
    common = {"prompt": args.prompt, "aspect_ratio": args.aspect_ratio,
              "quality": args.quality, "output_format": args.format,
              "response_format": "url"}
    if references:
        data, content_type = multipart(common, references)
        result = request(f"{base_url}/images/edits", key, data, content_type)
    else:
        data = json.dumps({**common, "model": "gpt-image-2"}).encode()
        result = request(f"{base_url}/images/generations", key, data, "application/json")

    image_url = result["data"][0]["url"]
    suffix = ".jpg" if args.format == "jpeg" else f".{args.format}"
    output = pathlib.Path(args.output).expanduser().resolve().with_suffix(suffix)
    output.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(image_url, timeout=360) as response:
        output.write_bytes(response.read())
    print(output)


if __name__ == "__main__":
    main()
