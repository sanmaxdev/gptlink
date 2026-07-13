from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from gptlink.config import Settings, settings
from gptlink.database import Database
from gptlink.image_provider import CodexImageProvider, GeneratedImage

IMAGE_MODELS = (
    "gpt-image-2",
    "gpt-image-2-low",
    "gpt-image-2-medium",
    "gpt-image-2-high",
    "gpt-image-2-auto",
)
MAX_REFERENCE_BYTES = 25 * 1024 * 1024


class AgentImageService:
    """Agent-friendly image operations shared by every MCP transport."""

    def __init__(self, app_settings: Settings = settings) -> None:
        self.settings = app_settings
        self.database = Database(app_settings.database_path)
        self.provider = CodexImageProvider(
            codex_home=app_settings.codex_home,
            hermes_home=app_settings.hermes_home,
            image_dir=app_settings.image_dir,
        )
        self._generation_limit = asyncio.Semaphore(2)

    def initialize(self) -> None:
        self.settings.ensure_directories()
        self.database.initialize()

    def status(self) -> dict[str, Any]:
        self.initialize()
        auth_source = self.provider.auth_source()
        active_keys = [key for key in self.database.list_api_keys() if not key["revoked_at"]]
        return {
            "ready": bool(auth_source),
            "authenticated": bool(auth_source),
            "auth_source": auth_source,
            "account": self.provider.auth_summary() if auth_source else None,
            "models": list(IMAGE_MODELS),
            "active_api_keys": len(active_keys),
            "output_directory": str(self.settings.image_dir),
            "message": (
                "GPTLink is ready for image generation."
                if auth_source
                else "No usable Codex or Hermes OpenAI-Codex session was found. Run Codex device login first."
            ),
        }

    def capabilities(self) -> dict[str, Any]:
        return {
            "generation": True,
            "editing": True,
            "variations": True,
            "reference_images": {"maximum": 16, "accepted": ["local path", "http(s) URL", "data URL"]},
            "aspect_ratio": {"minimum": "1:3", "maximum": "3:1"},
            "quality": ["auto", "low", "medium", "high"],
            "formats": ["png", "jpeg", "webp"],
            "sizes": "auto or WIDTHxHEIGHT; dimensions must be divisible by 16",
            "outputs_per_call": {"minimum": 1, "maximum": 10},
            "transparent_background": False,
        }

    def history(self, limit: int = 20) -> list[dict[str, Any]]:
        self.initialize()
        safe_limit = min(max(limit, 1), 100)
        return [
            {
                **image,
                "path": str(self.settings.image_dir / str(image["filename"])),
                "url": f"{self.settings.public_base_url}/files/{image['filename']}",
            }
            for image in self.database.list_images(safe_limit)
        ]

    def _allowed_roots(self) -> tuple[Path, ...]:
        roots = (self.settings.image_dir.resolve(), Path.cwd().resolve(), *self.settings.mcp_allowed_roots)
        return tuple(dict.fromkeys(roots))

    def _safe_local_path(self, value: str, *, must_exist: bool) -> Path:
        path = Path(value).expanduser().resolve()
        if not any(path == root or root in path.parents for root in self._allowed_roots()):
            roots = ", ".join(str(root) for root in self._allowed_roots())
            raise ValueError(f"Local path is outside GPTLink's allowed roots: {roots}")
        if must_exist and not path.is_file():
            raise ValueError(f"Reference image does not exist: {path}")
        return path

    def _reference_value(self, value: str) -> str:
        value = value.strip()
        if value.startswith("data:image/"):
            return value
        parsed = urlparse(value)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return value
        path = self._safe_local_path(value, must_exist=True)
        if path.stat().st_size > MAX_REFERENCE_BYTES:
            raise ValueError(f"Reference image exceeds 25 MB: {path}")
        return self.provider.image_bytes_to_data_url(path.read_bytes(), path.name)

    def _prepare_references(self, references: list[str] | None) -> list[str]:
        values = references or []
        if len(values) > 16:
            raise ValueError("At most 16 reference images are supported")
        return [self._reference_value(value) for value in values]

    def _copy_output(
        self, image: GeneratedImage, output_directory: str | None, output_filename: str | None
    ) -> Path:
        if not output_directory and not output_filename:
            return image.path.resolve()
        directory = self._safe_local_path(
            output_directory or str(self.settings.image_dir), must_exist=False
        )
        directory.mkdir(parents=True, exist_ok=True)
        suffix = ".jpg" if image.output_format == "jpeg" else f".{image.output_format}"
        filename = output_filename or image.path.name
        if Path(filename).name != filename:
            raise ValueError("output_filename must be a filename, not a path")
        if not Path(filename).suffix:
            filename += suffix
        destination = (directory / filename).resolve()
        if destination != image.path.resolve():
            shutil.copy2(image.path, destination)
        return destination

    def _record(self, image: GeneratedImage, prompt: str) -> None:
        self.database.record_image(
            image_id=image.id,
            filename=image.path.name,
            prompt=prompt,
            model=image.model,
            quality=image.quality,
            size=image.size,
        )

    async def generate(
        self,
        *,
        prompt: str,
        model: str = "gpt-image-2",
        reference_images: list[str] | None = None,
        mask_image: str | None = None,
        aspect_ratio: str | None = None,
        size: str = "auto",
        quality: str = "auto",
        output_format: str = "png",
        output_compression: int | None = None,
        moderation: str = "auto",
        n: int = 1,
        output_directory: str | None = None,
        output_filename: str | None = None,
        action: str | None = None,
    ) -> dict[str, Any]:
        self.initialize()
        prompt = prompt.strip()
        if not prompt:
            raise ValueError("Prompt is required")
        if not 1 <= n <= 10:
            raise ValueError("n must be between 1 and 10")
        if output_filename and n > 1:
            raise ValueError("output_filename can only be used when n is 1")
        if not self.provider.auth_source():
            raise RuntimeError("GPTLink is not authenticated. Complete Codex device login and retry.")
        references = self._prepare_references(reference_images)
        mask = self._reference_value(mask_image) if mask_image else None
        resolved_size = (
            self.provider.size_from_aspect_ratio(aspect_ratio)
            if aspect_ratio
            else self.provider.validate_size(size)
        )

        async def generate_one() -> GeneratedImage:
            async with self._generation_limit:
                return await asyncio.to_thread(
                    self.provider.generate,
                    prompt=prompt,
                    model=model,
                    size=resolved_size,
                    quality=quality,
                    output_format=output_format,
                    background="auto",
                    output_compression=output_compression,
                    moderation=moderation,
                    partial_images=0,
                    input_images=references,
                    input_image_mask=mask,
                    action=action or ("edit" if references else None),
                )

        generated = await asyncio.gather(*(generate_one() for _ in range(n)))
        results: list[dict[str, Any]] = []
        for image in generated:
            self._record(image, prompt)
            destination = self._copy_output(image, output_directory, output_filename)
            results.append(
                {
                    "id": image.id,
                    "path": str(destination),
                    "url": f"{self.settings.public_base_url}/files/{image.path.name}",
                    "format": image.output_format,
                    "quality": image.quality,
                    "size": image.size,
                    "revised_prompt": image.revised_prompt,
                    "usage": image.usage,
                }
            )
        return {
            "state": "completed",
            "count": len(results),
            "prompt": prompt,
            "images": results,
        }
