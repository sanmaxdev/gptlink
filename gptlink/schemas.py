from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateKeyRequest(StrictModel):
    name: str = Field(default="Default", max_length=80)


class ImageGenerationRequest(StrictModel):
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
    webhook_url: str | None = Field(default=None, max_length=2048)
    metadata: dict[str, str] = Field(default_factory=dict)

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
        if self.stream and self.webhook_url:
            raise ValueError("stream and webhook_url cannot be used together")
        if len(self.metadata) > 20 or any(
            len(str(key)) > 64 or len(str(value)) > 512
            for key, value in self.metadata.items()
        ):
            raise ValueError("metadata supports up to 20 keys of 64/512 characters")
        return self


class ImageJobRequest(StrictModel):
    operation: Literal["generate", "edit", "variation"] = "generate"
    prompt: str = Field(min_length=1, max_length=32_000)
    model: str = Field(default="gpt-image-2", max_length=80)
    reference_images: list[str] = Field(default_factory=list, max_length=16)
    mask_image: str | None = None
    aspect_ratio: str | None = None
    size: str = "auto"
    quality: Literal["low", "medium", "high", "auto"] = "auto"
    output_format: Literal["png", "jpeg", "webp"] = "png"
    output_compression: int | None = Field(default=None, ge=0, le=100)
    moderation: Literal["low", "auto"] = "auto"
    n: int = Field(default=1, ge=1, le=10)
    webhook_url: str | None = Field(default=None, max_length=2048)
    metadata: dict[str, str] = Field(default_factory=dict)

    @field_validator("prompt")
    @classmethod
    def clean_job_prompt(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Prompt cannot be blank")
        return value

    @field_validator("aspect_ratio")
    @classmethod
    def clean_job_ratio(cls, value: str | None) -> str | None:
        return ImageGenerationRequest.validate_aspect_ratio(value)

    @model_validator(mode="after")
    def validate_job(self) -> "ImageJobRequest":
        if self.operation in {"edit", "variation"} and not self.reference_images:
            raise ValueError(f"{self.operation} requires at least one reference image")
        if self.operation == "variation" and len(self.reference_images) != 1:
            raise ValueError("variation requires exactly one reference image")
        if self.mask_image and not self.reference_images:
            raise ValueError("mask_image requires reference_images")
        if self.aspect_ratio and self.size != "auto":
            raise ValueError("Use either size or aspect_ratio, not both")
        if self.output_format == "png" and self.output_compression is not None:
            raise ValueError("output_compression is only valid for jpeg or webp")
        encoded_size = sum(len(value.encode("utf-8")) for value in self.reference_images)
        encoded_size += len((self.mask_image or "").encode("utf-8"))
        if encoded_size > 64 * 1024 * 1024:
            raise ValueError("Inline reference data is limited to 64 MB per job")
        if len(self.metadata) > 20 or any(
            len(str(key)) > 64 or len(str(value)) > 512
            for key, value in self.metadata.items()
        ):
            raise ValueError("metadata supports up to 20 keys of 64/512 characters")
        return self


class ResponsesImageRequest(StrictModel):
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
