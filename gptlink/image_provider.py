from __future__ import annotations

import base64
import json
import math
import mimetypes
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator

import httpx

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    tomllib = None  # type: ignore[assignment]

CODEX_BASE_URL = "https://chatgpt.com/backend-api/codex"
# Codex only runs the image_generation tool through a chat model that the
# signed-in ChatGPT plan supports, and that set changes as models retire.
# The chat model is therefore resolved at runtime (see chat_model_candidates)
# instead of being pinned; this is only the last-resort default.
DEFAULT_CODEX_CHAT_MODEL = "gpt-6.1-sol"
CODEX_CHAT_MODEL_ENV = "GPTLINK_CODEX_MODEL"
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
    chat_model: str | None = None


class CodexImageProvider:
    def __init__(self, *, codex_home: Path, image_dir: Path, hermes_home: Path | None = None) -> None:
        self.codex_home = codex_home
        self.hermes_home = hermes_home or Path.home() / ".hermes"
        self.image_dir = image_dir
        self._working_chat_model: str | None = None

    def chat_model_candidates(self) -> list[str]:
        """Chat models to route image generation through, best first.

        A model that already succeeded in this process comes first, then the
        GPTLINK_CODEX_MODEL override (comma-separated), then the model the Codex
        CLI is configured with, then DEFAULT_CODEX_CHAT_MODEL.
        """
        candidates: list[str] = []
        if self._working_chat_model:
            candidates.append(self._working_chat_model)
        override = os.environ.get(CODEX_CHAT_MODEL_ENV, "")
        candidates.extend(part.strip() for part in override.split(",") if part.strip())
        configured = self._codex_configured_model()
        if configured:
            candidates.append(configured)
        candidates.append(DEFAULT_CODEX_CHAT_MODEL)
        return list(dict.fromkeys(candidates))

    def _codex_configured_model(self) -> str | None:
        """The `model` from Codex's config.toml, honouring an active profile."""
        if tomllib is None:
            return None
        try:
            config = tomllib.loads((self.codex_home / "config.toml").read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
            return None
        profile_name = config.get("profile")
        profiles = config.get("profiles")
        if isinstance(profile_name, str) and isinstance(profiles, dict):
            profile = profiles.get(profile_name)
            if isinstance(profile, dict):
                model = profile.get("model")
                if isinstance(model, str) and model.strip():
                    return model.strip()
        model = config.get("model")
        return model.strip() if isinstance(model, str) and model.strip() else None

    @staticmethod
    def is_unsupported_chat_model_error(status_code: int, body: str) -> bool:
        """True when Codex rejected the chat model itself, so another may work."""
        if status_code not in {400, 404}:
            return False
        text = body.lower()
        return "model" in text and any(
            marker in text
            for marker in ("not supported", "unsupported", "does not exist", "not found", "model_not_found")
        )

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
        timeout = httpx.Timeout(300, connect=30, read=300, write=30, pool=30)
        final_b64: str | None = None
        revised_prompt: str | None = None
        usage: dict[str, Any] | None = None
        partials: list[str] = []
        candidates = self.chat_model_candidates()
        rejected: list[str] = []
        chat_model = candidates[0]
        with httpx.Client(headers=self.build_headers(access_token), timeout=timeout) as client:
            for chat_model in candidates:
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
                    chat_model=chat_model,
                )
                with client.stream("POST", f"{CODEX_BASE_URL}/responses", json=payload) as response:
                    if response.is_error:
                        response.read()
                        message = response.text[:800]
                        if self.is_unsupported_chat_model_error(response.status_code, message):
                            rejected.append(f"{chat_model}: {message}")
                            continue
                        raise RuntimeError(
                            f"Codex image request failed ({response.status_code}): {message}"
                        )
                    self._working_chat_model = chat_model
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
                break
            else:
                raise RuntimeError(
                    "Codex rejected every chat model tried for image generation ("
                    + "; ".join(rejected)
                    + f"). Set {CODEX_CHAT_MODEL_ENV} to a model your ChatGPT plan can use in Codex."
                )
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
            chat_model=chat_model,
        )
        yield {"type": "completed", "image": generated}

    def _read_access_token(self) -> str:
        token = self._codex_cli_access_token() or self._hermes_access_token()
        if not token:
            raise RuntimeError("No fresh ChatGPT/Codex authentication was found in Codex CLI or Hermes")
        return token

    @staticmethod
    def _jwt_claims(token: str) -> dict[str, Any]:
        try:
            segment = token.split(".")[1]
            segment += "=" * (-len(segment) % 4)
            value = json.loads(base64.urlsafe_b64decode(segment))
            return value if isinstance(value, dict) else {}
        except (IndexError, ValueError, json.JSONDecodeError):
            return {}

    @classmethod
    def _fresh_token(cls, value: Any) -> str | None:
        if not isinstance(value, str) or not value.strip():
            return None
        token = value.strip()
        expires = cls._jwt_claims(token).get("exp")
        if isinstance(expires, (int, float)) and expires <= time.time() + 60:
            return None
        return token

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _codex_cli_access_token(self) -> str | None:
        auth = self._read_json(self.codex_home / "auth.json")
        return self._fresh_token((auth.get("tokens") or {}).get("access_token"))

    def _hermes_access_token(self) -> str | None:
        auth = self._read_json(self.hermes_home / "auth.json")
        provider = (auth.get("providers") or {}).get("openai-codex") or {}
        token = self._fresh_token((provider.get("tokens") or {}).get("access_token"))
        if token:
            return token
        pool = (auth.get("credential_pool") or {}).get("openai-codex") or []
        for entry in pool if isinstance(pool, list) else []:
            if not isinstance(entry, dict):
                continue
            reset_at = entry.get("last_error_reset_at")
            if isinstance(reset_at, (int, float)) and reset_at > time.time():
                continue
            if entry.get("last_status") in {"quarantined", "invalid"}:
                continue
            token = self._fresh_token(entry.get("access_token"))
            if token:
                return token
        return None

    def auth_source(self) -> str | None:
        if self._codex_cli_access_token():
            return "codex_cli"
        if self._hermes_access_token():
            return "hermes"
        return None

    def auth_summary(self) -> dict[str, Any]:
        token = self._codex_cli_access_token() or self._hermes_access_token() or ""
        claims = self._jwt_claims(token)
        auth_claims = claims.get("https://api.openai.com/auth") or {}
        return {
            "type": "chatgpt",
            "planType": auth_claims.get("chatgpt_plan_type") or "unknown",
            "source": self.auth_source(),
        }

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
        chat_model: str = DEFAULT_CODEX_CHAT_MODEL,
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
            "model": chat_model,
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
