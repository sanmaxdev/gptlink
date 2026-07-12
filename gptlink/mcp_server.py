from __future__ import annotations

import argparse
import json
from typing import Any

from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import AnyHttpUrl
from urllib.parse import urlparse

from gptlink.agent_service import AgentImageService, IMAGE_MODELS
from gptlink.config import settings
from gptlink.database import Database


class GPTLinkTokenVerifier(TokenVerifier):
    def __init__(self) -> None:
        self.database = Database(settings.database_path)

    async def verify_token(self, token: str) -> AccessToken | None:
        settings.ensure_directories()
        self.database.initialize()
        if not self.database.validate_api_key(token):
            return None
        return AccessToken(
            token=token,
            client_id="gptlink-agent",
            scopes=["images:generate", "images:read"],
        )


def create_mcp_server(*, require_auth: bool) -> FastMCP:
    service = AgentImageService()
    public_url = urlparse(settings.public_base_url)
    public_host = public_url.netloc
    allowed_hosts = ["localhost:*", "127.0.0.1:*", "[::1]:*"]
    allowed_origins = ["http://localhost:*", "http://127.0.0.1:*", "http://[::1]:*"]
    if public_host:
        allowed_hosts.append(public_host)
        allowed_origins.append(f"{public_url.scheme}://{public_host}")
    options: dict[str, Any] = {}
    if require_auth:
        options.update(
            token_verifier=GPTLinkTokenVerifier(),
            auth=AuthSettings(
                issuer_url=AnyHttpUrl(settings.public_base_url),
                resource_server_url=AnyHttpUrl(f"{settings.public_base_url}/mcp/"),
                required_scopes=[],
            ),
        )
    server = FastMCP(
        "GPTLink Images",
        instructions=(
            "Generate and edit images through the user's authenticated GPTLink service. "
            "Check gptlink_status first when a request fails. Prefer file paths over embedding base64 output."
        ),
        website_url="https://github.com/sanmaxdev/gptlink",
        streamable_http_path="/",
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=list(dict.fromkeys(allowed_hosts)),
            allowed_origins=list(dict.fromkeys(allowed_origins)),
        ),
        **options,
    )

    @server.tool()
    def gptlink_status() -> dict[str, Any]:
        """Check GPTLink authentication, models, and readiness before image work."""
        return service.status()

    @server.tool()
    def gptlink_models() -> dict[str, Any]:
        """List GPTLink image models and supported generation controls."""
        return {"models": list(IMAGE_MODELS), "capabilities": service.capabilities()}

    @server.tool()
    async def gptlink_generate(
        prompt: str,
        aspect_ratio: str | None = None,
        size: str = "auto",
        quality: str = "auto",
        output_format: str = "png",
        output_compression: int | None = None,
        moderation: str = "auto",
        n: int = 1,
        output_directory: str | None = None,
        output_filename: str | None = None,
    ) -> dict[str, Any]:
        """Generate images from text. Use either aspect_ratio (for example 16:9) or an exact size."""
        return await service.generate(
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            size=size,
            quality=quality,
            output_format=output_format,
            output_compression=output_compression,
            moderation=moderation,
            n=n,
            output_directory=output_directory,
            output_filename=output_filename,
        )

    @server.tool()
    async def gptlink_edit(
        prompt: str,
        reference_images: list[str],
        mask_image: str | None = None,
        aspect_ratio: str | None = None,
        size: str = "auto",
        quality: str = "auto",
        output_format: str = "png",
        output_compression: int | None = None,
        n: int = 1,
        output_directory: str | None = None,
        output_filename: str | None = None,
    ) -> dict[str, Any]:
        """Edit or combine up to 16 local, HTTP(S), or data-URL reference images; an optional mask limits edits."""
        if not reference_images:
            raise ValueError("At least one reference image is required for editing")
        return await service.generate(
            prompt=prompt,
            reference_images=reference_images,
            mask_image=mask_image,
            aspect_ratio=aspect_ratio,
            size=size,
            quality=quality,
            output_format=output_format,
            output_compression=output_compression,
            n=n,
            output_directory=output_directory,
            output_filename=output_filename,
            action="edit",
        )

    @server.tool()
    async def gptlink_variation(
        reference_image: str,
        instructions: str = "Create a distinct high-quality variation while preserving the subject and visual identity.",
        aspect_ratio: str | None = None,
        size: str = "auto",
        quality: str = "auto",
        n: int = 1,
        output_directory: str | None = None,
    ) -> dict[str, Any]:
        """Create one or more visually distinct variations of a reference image."""
        return await service.generate(
            prompt=instructions,
            reference_images=[reference_image],
            aspect_ratio=aspect_ratio,
            size=size,
            quality=quality,
            n=n,
            output_directory=output_directory,
            action="edit",
        )

    @server.tool()
    def gptlink_history(limit: int = 20) -> dict[str, Any]:
        """Return recent generated image metadata, file paths, and URLs without image base64 data."""
        return {"images": service.history(limit)}

    @server.resource("gptlink://capabilities")
    def capabilities_resource() -> str:
        """Machine-readable GPTLink image capabilities."""
        return json.dumps(service.capabilities(), indent=2)

    @server.prompt(title="Create a production-ready image")
    def production_image_prompt(subject: str, purpose: str, style: str = "photorealistic") -> str:
        """Build a concise prompt for a polished image asset."""
        return (
            f"Create a {style} image of {subject} for {purpose}. Specify composition, lighting, "
            "materials, camera perspective, background, and what must not appear. Then call "
            "gptlink_generate with the most suitable aspect ratio and quality."
        )

    return server


remote_mcp = create_mcp_server(require_auth=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="GPTLink MCP server")
    parser.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    parser.add_argument("--host", default=settings.host)
    parser.add_argument("--port", type=int, default=8790)
    args = parser.parse_args()
    settings.ensure_directories()
    Database(settings.database_path).initialize()
    server = create_mcp_server(require_auth=args.transport == "http")
    if args.transport == "stdio":
        server.run(transport="stdio")
    else:
        server.settings.host = args.host
        server.settings.port = args.port
        server.run(transport="streamable-http")


if __name__ == "__main__":
    main()
