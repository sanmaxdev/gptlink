from __future__ import annotations

import base64
import json
import math
import mimetypes
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator

import httpx

CODEX_BASE_URL = "https://chatgpt.com/backend-api/codex"
CODEX_CHAT_MODEL = "gpt-5.5"
IMAGE_MODEL = "gpt-image-2"
MIN_PIXELS = 655_360
MAX_PIXELS = 8_294_400
MAX_EDGE = 3_840
SUPPORTED_QUALITIES = {"low", "medium", "high", "auto"}
SUPPORTED_FORMATS = {"png", "jpeg", "webp"}
SUPPORTED_BACKGROUNDS = {"auto", "opaque"}
SUPPORTED_MODERATION = {"auto", "low"}
MODEL_QUALITY = {
    "gpt-image-2-low": "low",
    "gpt-image-2-medium": "medium",
    "gpt-image-2-high": "high",
    "gpt-image-2-auto": "auto",
}


@dataclass(frozen=True)
class GeneratedImage:
    id: str
    path: Path
    base64_data: str
    model: str
    quality: str
    size: str
    output_format: str
    background: str
    revised_prompt: str | None = None
    usage: dict[str, Any] | None = None
    partial_images: list[str] = field(default_factory=list)


class CodexImageProvider:
    def __init__(self, *, codex_home: Path, image_dir: Path) -> None:
        self.codex_home = codex_home
        self.image_dir = image_dir

    def generate(
        self,
        *,
        prompt: str,
        model: str,
        size: str,
        quality: str,
        output_format: str,
        background: str,
        output_compression: int | None = None,
        moderation: str = "auto",
        partial_images: int = 0,
        input_images: list[str] | None = None,
        input_image_mask: str | None = None,
        action: str | None = None,
    ) -> GeneratedImage:
        completed: GeneratedImage | None = None
        for event in self.stream_generate(
            prompt=prompt,
            model=model,
            size=size,
            quality=quality,
            output_format=output_format,
            background=background,
            output_compression=output_compression,
            moderation=moderation,
            partial_images=partial_images,
            input_images=input_images,
            input_image_mask=input_image_mask,
            action=action,
        ):
            if event["type"] == "completed":
                completed = event["image"]
        if completed is None:
            raise RuntimeError("Codex completed without returning an image")
        return completed

    def stream_generate(
        self,
        *,
        prompt: str,
        model: str,
        size: str,
        quality: str,
        output_format: str,
        background: str,
        output_compression: int | None = None,
        moderation: str = "auto",
        partial_images: int = 0,
        input_images: list[str] | None = None,
        input_image_mask: str | None = None,
        action: str | None = None,
    ) -> Iterator[dict[str, Any]]:
        access_token = self._read_access_token()
        resolved_quality = self.resolve_quality(model, quality)
        resolved_size = self.validate_size(size)
        payload = self.build_payload(
            prompt=prompt,
            size=resolved_size,
            quality=resolved_quality,
            output_format=output_format,
            background=background,
            output_compression=output_compression,
            moderation=moderation,
            partial_images=partial_images,
            input_images=input_images or [],
            input_image_mask=input_image_mask,
            action=action,
        )
        timeout = httpx.Timeout(300, connect=30, read=300, write=30, pool=30)
        final_b64: str | None = None
        revised_prompt: str | None = None
        usage: dict[str, Any] | None = None
        partials: list[str] = []
        with httpx.Client(headers=self.build_headers(access_token), timeout=timeout) as client:
            with client.stream("POST", f"{CODEX_BASE_URL}/responses", json=payload) as response:
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    response.read()
                    message = response.text[:800]
                    raise RuntimeError(
                        f"Codex image request failed ({response.status_code}): {message}"
                    ) from exc
                for event in self.iter_sse_json(response.iter_lines()):
                    partial_b64 = self.extract_partial_image_b64(event)
                    if partial_b64 and (not partials or partials[-1] != partial_b64):
                        partials.append(partial_b64)
                        yield {
                            "type": "partial",
                            "index": len(partials) - 1,
                            "base64_data": partial_b64,
                        }
                    candidate = self.extract_image_b64(event)
                    if candidate:
                        final_b64 = candidate
                    revised_prompt = self.extract_revised_prompt(event) or revised_prompt
                    usage = self.extract_usage(event) or usage
        if not final_b64:
            raise RuntimeError("Codex completed without returning an image")
        image_id = f"img_{uuid.uuid4().hex}"
        extension = "jpg" if output_format == "jpeg" else output_format
        path = self.image_dir / f"{image_id}.{extension}"
        path.write_bytes(base64.b64decode(final_b64, validate=True))
        generated = GeneratedImage(
            id=image_id,
            path=path,
            base64_data=final_b64,
            model=model,
            quality=resolved_quality,
            size=resolved_size,
            output_format=output_format,
            background=background,
            revised_prompt=revised_prompt,
            usage=usage,
            partial_images=partials,
        )
        yield {"type": "completed", "image": generated}

    def _read_access_token(self) -> str:
        auth_path = self.codex_home / "auth.json"
        try:
            auth = json.loads(auth_path.read_text(encoding="utf-8"))
            token = auth.get("tokens", {}).get("access_token")
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("Codex authentication could not be read") from exc
        if not isinstance(token, str) or not token.strip():
            raise RuntimeError("Not logged into ChatGPT/Codex")
        return token.strip()

    @staticmethod
    def resolve_quality(model: str, quality: str) -> str:
        resolved = MODEL_QUALITY.get(model, quality)
        if resolved not in SUPPORTED_QUALITIES:
            raise ValueError(f"Unsupported quality: {resolved}")
        return resolved

    @staticmethod
    def validate_size(size: str) -> str:
        if size == "auto":
            return size
        match = re.fullmatch(r"(\d+)x(\d+)", size.strip().lower())
        if not match:
            raise ValueError("size must be 'auto' or WIDTHxHEIGHT")
        width, height = map(int, match.groups())
        if width % 16 or height % 16:
            raise ValueError("Image width and height must be divisible by 16")
        if max(width, height) > MAX_EDGE:
            raise ValueError(f"Maximum image edge is {MAX_EDGE}px")
        ratio = width / height
        if not 1 / 3 <= ratio <= 3:
            raise ValueError("Image aspect ratio must be between 1:3 and 3:1")
        pixels = width * height
        if not MIN_PIXELS <= pixels <= MAX_PIXELS:
            raise ValueError(
                f"Image must contain between {MIN_PIXELS:,} and {MAX_PIXELS:,} pixels"
            )
        return f"{width}x{height}"

    @staticmethod
    def size_from_aspect_ratio(aspect_ratio: str, target_pixels: int = 1_048_576) -> str:
        match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*:\s*(\d+(?:\.\d+)?)\s*", aspect_ratio)
        if not match:
            raise ValueError("aspect_ratio must look like 16:9")
        ratio = float(match.group(1)) / float(match.group(2))
        if not 1 / 3 <= ratio <= 3:
            raise ValueError("aspect_ratio must be between 1:3 and 3:1")
        width = round(math.sqrt(target_pixels * ratio) / 16) * 16
        height = round(math.sqrt(target_pixels / ratio) / 16) * 16
        pixels = width * height
        if pixels < MIN_PIXELS:
            scale = math.sqrt(MIN_PIXELS / pixels)
            width = math.ceil(width * scale / 16) * 16
            height = math.ceil(height * scale / 16) * 16
        return CodexImageProvider.validate_size(f"{width}x{height}")

    @staticmethod
    def build_headers(access_token: str) -> dict[str, str]:
        headers = {
            "Accept": "text/event-stream",
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "User-Agent": "codex_cli_rs/0.144.1 (GPTLink)",
            "originator": "codex_cli_rs",
        }
        try:
            payload_segment = access_token.split(".")[1]
            payload_segment += "=" * (-len(payload_segment) % 4)
            claims = json.loads(base64.urlsafe_b64decode(payload_segment))
            account_id = claims.get("https://api.openai.com/auth", {}).get(
                "chatgpt_account_id"
            )
            if isinstance(account_id, str) and account_id:
                headers["ChatGPT-Account-ID"] = account_id
        except (IndexError, ValueError, json.JSONDecodeError):
            pass
        return headers

    @staticmethod
    def build_payload(
        *,
        prompt: str,
        size: str,
        quality: str,
        output_format: str,
        background: str,
        output_compression: int | None,
        moderation: str,
        partial_images: int,
        input_images: list[str],
        input_image_mask: str | None,
        action: str | None,
    ) -> dict[str, Any]:
        CodexImageProvider.validate_size(size)
        if output_format not in SUPPORTED_FORMATS:
            raise ValueError(f"Unsupported output format: {output_format}")
        if background not in SUPPORTED_BACKGROUNDS:
            raise ValueError("GPT Image 2 supports only auto or opaque backgrounds")
        if moderation not in SUPPORTED_MODERATION:
            raise ValueError(f"Unsupported moderation mode: {moderation}")
        if not 0 <= partial_images <= 3:
            raise ValueError("partial_images must be between 0 and 3")
        resolved_action = action or ("edit" if input_images else "generate")
        if resolved_action not in {"auto", "generate", "edit"}:
            raise ValueError("action must be auto, generate, or edit")
        if resolved_action == "edit" and not input_images:
            raise ValueError("action=edit requires at least one input image")
        if output_compression is not None:
            if output_format == "png":
                raise ValueError("output_compression is only valid for jpeg or webp")
            if not 0 <= output_compression <= 100:
                raise ValueError("output_compression must be between 0 and 100")
        content: list[dict[str, str]] = [{"type": "input_text", "text": prompt}]
        content.extend({"type": "input_image", "image_url": image} for image in input_images)
        tool: dict[str, Any] = {
            "type": "image_generation",
            "model": IMAGE_MODEL,
            "action": resolved_action,
            "size": size,
            "quality": quality,
            "output_format": output_format,
            "background": background,
            "moderation": moderation,
            "partial_images": partial_images,
        }
        if output_compression is not None:
            tool["output_compression"] = output_compression
        if input_image_mask:
            tool["input_image_mask"] = {"image_url": input_image_mask}
        return {
            "model": CODEX_CHAT_MODEL,
            "store": False,
            "instructions": (
                "Fulfill the user's image request by calling the image_generation "
                "tool. Return the generated image without additional tasks."
            ),
            "input": [{"type": "message", "role": "user", "content": content}],
            "tools": [tool],
            "tool_choice": {
                "type": "allowed_tools",
                "mode": "required",
                "tools": [{"type": "image_generation"}],
            },
            "stream": True,
        }

    @staticmethod
    def iter_sse_json(lines: Iterable[str]) -> Iterable[dict[str, Any]]:
        event_name: str | None = None
        data_lines: list[str] = []

        def flush() -> dict[str, Any] | None:
            nonlocal event_name, data_lines
            if not data_lines:
                event_name = None
                return None
            raw_data = "\n".join(data_lines).strip()
            current_event = event_name
            event_name = None
            data_lines = []
            if not raw_data or raw_data == "[DONE]":
                return None
            payload = json.loads(raw_data)
            if isinstance(payload, dict) and current_event and "type" not in payload:
                payload = {**payload, "type": current_event}
            return payload if isinstance(payload, dict) else None

        for raw_line in lines:
            line = str(raw_line)
            if not line:
                payload = flush()
                if payload is not None:
                    yield payload
            elif line.startswith("event:"):
                event_name = line[6:].strip()
            elif line.startswith("data:"):
                data_lines = [*data_lines, line[5:].lstrip()]
        payload = flush()
        if payload is not None:
            yield payload

    @staticmethod
    def extract_image_b64(value: Any) -> str | None:
        found: str | None = None
        if isinstance(value, dict):
            if value.get("type") == "image_generation_call":
                result = value.get("result")
                if isinstance(result, str) and result:
                    found = result
            for child in value.values():
                nested = CodexImageProvider.extract_image_b64(child)
                if nested:
                    found = nested
        elif isinstance(value, list):
            for child in value:
                nested = CodexImageProvider.extract_image_b64(child)
                if nested:
                    found = nested
        return found

    @staticmethod
    def extract_partial_image_b64(value: Any) -> str | None:
        if isinstance(value, dict):
            partial = value.get("partial_image_b64")
            if isinstance(partial, str) and partial:
                return partial
            for child in value.values():
                nested = CodexImageProvider.extract_partial_image_b64(child)
                if nested:
                    return nested
        elif isinstance(value, list):
            for child in value:
                nested = CodexImageProvider.extract_partial_image_b64(child)
                if nested:
                    return nested
        return None

    @staticmethod
    def extract_revised_prompt(value: Any) -> str | None:
        if isinstance(value, dict):
            prompt = value.get("revised_prompt")
            if isinstance(prompt, str) and prompt:
                return prompt
            for child in value.values():
                nested = CodexImageProvider.extract_revised_prompt(child)
                if nested:
                    return nested
        elif isinstance(value, list):
            for child in value:
                nested = CodexImageProvider.extract_revised_prompt(child)
                if nested:
                    return nested
        return None

    @staticmethod
    def extract_usage(value: Any) -> dict[str, Any] | None:
        if isinstance(value, dict):
            usage = value.get("usage")
            if isinstance(usage, dict):
                return usage
            for child in value.values():
                nested = CodexImageProvider.extract_usage(child)
                if nested:
                    return nested
        elif isinstance(value, list):
            for child in value:
                nested = CodexImageProvider.extract_usage(child)
                if nested:
                    return nested
        return None

    @staticmethod
    def image_bytes_to_data_url(data: bytes, filename: str) -> str:
        mime, _ = mimetypes.guess_type(filename)
        allowed = {"image/png", "image/jpeg", "image/webp", "image/gif"}
        mime = mime if mime in allowed else "image/png"
        encoded = base64.b64encode(data).decode("ascii")
        return f"data:{mime};base64,{encoded}"
