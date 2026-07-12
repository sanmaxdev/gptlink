from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class CreateKeyRequest(BaseModel):
    name: str = Field(default="Default", max_length=80)


class ImageGenerationRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=32_000)
    model: str = "gpt-image-2"
    n: int = Field(default=1, ge=1, le=10)
    size: str = "auto"
    aspect_ratio: str | None = None
    quality: Literal["low", "medium", "high", "auto"] = "auto"
    response_format: Literal["url", "b64_json"] = "b64_json"
    output_format: Literal["png", "jpeg", "webp"] = "png"
    output_compression: int | None = Field(default=None, ge=0, le=100)
    background: Literal["opaque", "auto"] = "auto"
    moderation: Literal["low", "auto"] = "auto"
    partial_images: int = Field(default=0, ge=0, le=3)
    stream: bool = False
    user: str | None = Field(default=None, max_length=256)

    @field_validator("prompt")
    @classmethod
    def strip_prompt(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Prompt cannot be blank")
        return stripped

    @field_validator("aspect_ratio")
    @classmethod
    def validate_aspect_ratio(cls, value: str | None) -> str | None:
        if value is None:
            return None
        match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*:\s*(\d+(?:\.\d+)?)\s*", value)
        if not match:
            raise ValueError("aspect_ratio must look like 16:9")
        width_ratio, height_ratio = map(float, match.groups())
        ratio = width_ratio / height_ratio
        if not 1 / 3 <= ratio <= 3:
            raise ValueError("aspect_ratio must be between 1:3 and 3:1")
        return f"{match.group(1)}:{match.group(2)}"

    @model_validator(mode="after")
    def validate_output_options(self) -> "ImageGenerationRequest":
        if self.output_format == "png" and self.output_compression is not None:
            raise ValueError("output_compression is only valid for jpeg or webp")
        if self.aspect_ratio and self.size != "auto":
            raise ValueError("Use either size or aspect_ratio, not both")
        if self.stream and self.partial_images == 0:
            self.partial_images = 1
        return self


class ResponsesImageRequest(BaseModel):
    model: str = "gpt-5.5"
    input: str | list[dict[str, Any]]
    tools: list[dict[str, Any]] = Field(min_length=1)
    tool_choice: dict[str, Any] | str | None = None
    stream: bool = False
    store: bool = False

    @model_validator(mode="after")
    def require_image_tool(self) -> "ResponsesImageRequest":
        if not any(tool.get("type") == "image_generation" for tool in self.tools):
            raise ValueError("This gateway's Responses endpoint requires an image_generation tool")
        return self

