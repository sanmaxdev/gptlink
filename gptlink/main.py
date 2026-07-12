from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from gptlink.codex_rpc import CodexAppServer, tolerate_codex_failure
from gptlink.config import settings
from gptlink.database import Database
from gptlink.image_provider import CodexImageProvider, GeneratedImage
from gptlink.schemas import CreateKeyRequest, ImageGenerationRequest, ResponsesImageRequest

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

database = Database(settings.database_path)
codex = CodexAppServer()
image_provider = CodexImageProvider(
    codex_home=settings.codex_home,
    hermes_home=settings.hermes_home,
    image_dir=settings.image_dir,
)
generation_lock = asyncio.Semaphore(2)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.ensure_directories()
    database.initialize()
    try:
        await codex.start()
    except Exception:
        logger.exception("Codex app-server did not start; the dashboard can still load")
    yield
    await codex.stop()


app = FastAPI(
    title="GPTLink",
    version="0.3.0",
    description="Local GPT Image 2 API gateway backed by ChatGPT/Codex auth.",
    lifespan=lifespan,
)


def openai_error(message: str, *, error_type: str, code: str | None = None) -> dict[str, Any]:
    return {"error": {"message": message, "type": error_type, "param": None, "code": code}}


@app.exception_handler(HTTPException)
async def handle_http_exception(_: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else json.dumps(exc.detail)
    error_type = "authentication_error" if exc.status_code == 401 else "invalid_request_error"
    return JSONResponse(openai_error(detail, error_type=error_type), status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def handle_validation_exception(_: Request, exc: RequestValidationError) -> JSONResponse:
    first = exc.errors()[0] if exc.errors() else {}
    message = str(first.get("msg", "Request validation failed")).removeprefix("Value error, ")
    return JSONResponse(
        openai_error(message, error_type="invalid_request_error", code="validation_error"),
        status_code=400,
    )


@app.exception_handler(ValueError)
async def handle_value_error(_: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(
        openai_error(str(exc), error_type="invalid_request_error", code="validation_error"),
        status_code=400,
    )


def require_api_key(authorization: Annotated[str | None, Header()] = None) -> None:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer API key")
    if not database.validate_api_key(authorization[7:].strip()):
        raise HTTPException(status_code=401, detail="Invalid or revoked API key")


async def refresh_codex_auth() -> dict[str, Any]:
    if image_provider.auth_source() == "hermes":
        return {"account": image_provider.auth_summary()}
    if not codex.process or codex.process.returncode is not None:
        await codex.start()
    return await codex.request("account/read", {"refreshToken": True})


def record_generated_image(image: GeneratedImage, prompt: str) -> None:
    database.record_image(
        image_id=image.id,
        filename=image.path.name,
        prompt=prompt,
        model=image.model,
        quality=image.quality,
        size=image.size,
    )


def image_response_item(image: GeneratedImage, response_format: str, base_url: str) -> dict[str, Any]:
    item: dict[str, Any] = (
        {"b64_json": image.base64_data}
        if response_format == "b64_json"
        else {"url": f"{base_url}/files/{image.path.name}"}
    )
    if image.revised_prompt:
        item["revised_prompt"] = image.revised_prompt
    return item


async def generate_one(
    *,
    prompt: str,
    model: str,
    size: str,
    quality: str,
    output_format: str,
    background: str,
    output_compression: int | None,
    moderation: str,
    partial_images: int,
    input_images: list[str] | None = None,
    input_image_mask: str | None = None,
    action: str | None = None,
) -> GeneratedImage:
    async with generation_lock:
        return await asyncio.to_thread(
            image_provider.generate,
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
        )


async def generate_many(*, count: int, **kwargs: Any) -> list[GeneratedImage]:
    return await asyncio.gather(*(generate_one(**kwargs) for _ in range(count)))


def sse(payload: dict[str, Any] | str) -> str:
    data = payload if isinstance(payload, str) else json.dumps(payload, separators=(",", ":"))
    return f"data: {data}\n\n"


def image_stream(
    *,
    count: int,
    prompt: str,
    model: str,
    size: str,
    quality: str,
    output_format: str,
    background: str,
    output_compression: int | None,
    moderation: str,
    partial_images: int,
    response_format: str,
    base_url: str,
    input_images: list[str] | None = None,
    input_image_mask: str | None = None,
    action: str | None = None,
):
    def iterator():
        try:
            for output_index in range(count):
                for event in image_provider.stream_generate(
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
                    if event["type"] == "partial":
                        yield sse(
                            {
                                "type": "image_generation.partial_image",
                                "output_index": output_index,
                                "partial_image_index": event["index"],
                                "b64_json": event["base64_data"],
                            }
                        )
                    else:
                        image = event["image"]
                        record_generated_image(image, prompt)
                        yield sse(
                            {
                                "type": "image_generation.completed",
                                "output_index": output_index,
                                **image_response_item(image, response_format, base_url),
                                "size": image.size,
                                "quality": image.quality,
                                "background": image.background,
                                "output_format": image.output_format,
                                "usage": image.usage,
                            }
                        )
            yield sse("[DONE]")
        except Exception as exc:
            yield sse({"type": "error", **openai_error(str(exc), error_type="api_error")})

    return StreamingResponse(iterator(), media_type="text/event-stream")


def resolve_size(size: str, aspect_ratio: str | None) -> str:
    return image_provider.size_from_aspect_ratio(aspect_ratio) if aspect_ratio else image_provider.validate_size(size)


async def upload_to_data_url(upload: UploadFile) -> str:
    data = await upload.read()
    if not data or len(data) > 25 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Each image must be between 1 byte and 25 MB")
    return image_provider.image_bytes_to_data_url(data, upload.filename or "image.png")


@app.get("/api/status")
async def get_status() -> dict[str, Any]:
    account, limits, usage = await asyncio.gather(
        tolerate_codex_failure(codex.request("account/read", {"refreshToken": False})),
        tolerate_codex_failure(codex.request("account/rateLimits/read", {})),
        tolerate_codex_failure(codex.request("account/usage/read", {})),
    )
    auth_source = image_provider.auth_source()
    if auth_source and account.get("account"):
        account = {**account, "account": {**account["account"], "source": auth_source}}
    elif auth_source == "hermes":
        account = {"account": image_provider.auth_summary()}
    return {
        "codex": account,
        "rate_limits": limits,
        "usage": usage,
        "gateway": {
            "url": f"http://{settings.host}:{settings.port}/v1",
            "keys": len([key for key in database.list_api_keys() if not key["revoked_at"]]),
        },
    }


@app.post("/api/auth/login")
async def login() -> dict[str, Any]:
    return await codex.request(
        "account/login/start",
        {"type": "chatgpt", "useHostedLoginSuccessPage": True, "appBrand": "codex"},
    )


@app.post("/api/auth/device-code")
async def login_device_code() -> dict[str, Any]:
    return await codex.request("account/login/start", {"type": "chatgptDeviceCode"})


@app.post("/api/auth/logout")
async def logout() -> dict[str, Any]:
    return await codex.request("account/logout", {})


@app.get("/api/keys")
async def list_keys() -> dict[str, Any]:
    return {"data": database.list_api_keys()}


@app.post("/api/keys")
async def create_key(payload: CreateKeyRequest) -> dict[str, Any]:
    return {"data": database.create_api_key(payload.name).__dict__}


@app.delete("/api/keys/{key_id}")
async def revoke_key(key_id: int) -> dict[str, bool]:
    if not database.revoke_api_key(key_id):
        raise HTTPException(status_code=404, detail="Active API key not found")
    return {"success": True}


@app.get("/api/images")
async def list_images() -> dict[str, Any]:
    return {
        "data": [{**image, "url": f"/files/{image['filename']}"} for image in database.list_images()]
    }


@app.get("/v1/models", dependencies=[Depends(require_api_key)])
async def list_models() -> dict[str, Any]:
    models = ("gpt-image-2", "gpt-image-2-low", "gpt-image-2-medium", "gpt-image-2-high", "gpt-image-2-auto")
    return {"object": "list", "data": [{"id": model, "object": "model", "owned_by": "openai-codex"} for model in models]}


@app.post("/v1/images/generations", dependencies=[Depends(require_api_key)])
async def generate_image(payload: ImageGenerationRequest, request: Request):
    await refresh_codex_auth()
    resolved_size = resolve_size(payload.size, payload.aspect_ratio)
    base_url = str(request.base_url).rstrip("/")
    kwargs = {
        "prompt": payload.prompt,
        "model": payload.model,
        "size": resolved_size,
        "quality": payload.quality,
        "output_format": payload.output_format,
        "background": payload.background,
        "output_compression": payload.output_compression,
        "moderation": payload.moderation,
        "partial_images": payload.partial_images,
    }
    if payload.stream:
        return image_stream(
            count=payload.n,
            response_format=payload.response_format,
            base_url=base_url,
            **kwargs,
        )
    try:
        images = await generate_many(count=payload.n, **kwargs)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    for image in images:
        record_generated_image(image, payload.prompt)
    return {
        "created": int(time.time()),
        "background": images[0].background,
        "data": [image_response_item(image, payload.response_format, base_url) for image in images],
        "output_format": images[0].output_format,
        "quality": images[0].quality,
        "size": images[0].size,
        "usage": images[0].usage,
    }


@app.post("/v1/images/edits", dependencies=[Depends(require_api_key)])
async def edit_image(
    request: Request,
    image: Annotated[list[UploadFile], File()],
    prompt: Annotated[str, Form(min_length=1, max_length=32_000)],
    mask: Annotated[UploadFile | None, File()] = None,
    model: Annotated[str, Form()] = "gpt-image-2",
    n: Annotated[int, Form(ge=1, le=10)] = 1,
    size: Annotated[str, Form()] = "auto",
    aspect_ratio: Annotated[str | None, Form()] = None,
    quality: Annotated[str, Form()] = "auto",
    response_format: Annotated[str, Form()] = "b64_json",
    output_format: Annotated[str, Form()] = "png",
    output_compression: Annotated[int | None, Form(ge=0, le=100)] = None,
    background: Annotated[str, Form()] = "auto",
    moderation: Annotated[str, Form()] = "auto",
    partial_images: Annotated[int, Form(ge=0, le=3)] = 0,
    stream: Annotated[bool, Form()] = False,
):
    if len(image) > 16:
        raise HTTPException(status_code=400, detail="At most 16 input images are supported")
    input_images = [await upload_to_data_url(upload) for upload in image]
    input_mask = await upload_to_data_url(mask) if mask else None
    await refresh_codex_auth()
    resolved_size = resolve_size(size, aspect_ratio)
    base_url = str(request.base_url).rstrip("/")
    kwargs = {
        "prompt": prompt.strip(), "model": model, "size": resolved_size, "quality": quality,
        "output_format": output_format, "background": background,
        "output_compression": output_compression, "moderation": moderation,
        "partial_images": partial_images, "input_images": input_images,
        "input_image_mask": input_mask,
    }
    if stream:
        return image_stream(count=n, response_format=response_format, base_url=base_url, **kwargs)
    try:
        images = await generate_many(count=n, **kwargs)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    for generated in images:
        record_generated_image(generated, prompt.strip())
    return {
        "created": int(time.time()),
        "data": [image_response_item(item, response_format, base_url) for item in images],
        "background": images[0].background,
        "output_format": images[0].output_format,
        "quality": images[0].quality,
        "size": images[0].size,
        "usage": images[0].usage,
    }


@app.post("/v1/images/variations", dependencies=[Depends(require_api_key)])
async def create_variation(
    request: Request,
    image: Annotated[UploadFile, File()],
    n: Annotated[int, Form(ge=1, le=10)] = 1,
    size: Annotated[str, Form()] = "auto",
    response_format: Annotated[str, Form()] = "b64_json",
):
    reference = await upload_to_data_url(image)
    await refresh_codex_auth()
    resolved_size = image_provider.validate_size(size)
    prompt = "Create a distinct high-quality variation of this reference image while preserving its subject and visual identity."
    images = await generate_many(
        count=n, prompt=prompt, model="gpt-image-2", size=resolved_size, quality="auto",
        output_format="png", background="auto", output_compression=None,
        moderation="auto", partial_images=0, input_images=[reference], input_image_mask=None,
    )
    for generated in images:
        record_generated_image(generated, prompt)
    base_url = str(request.base_url).rstrip("/")
    return {
        "created": int(time.time()),
        "data": [image_response_item(item, response_format, base_url) for item in images],
        "gptlink_emulated": True,
    }


def parse_responses_input(value: str | list[dict[str, Any]]) -> tuple[str, list[str]]:
    if isinstance(value, str):
        return value, []
    prompt_parts: list[str] = []
    images: list[str] = []
    for item in value:
        content = item.get("content", [])
        if isinstance(content, str):
            prompt_parts.append(content)
            continue
        for part in content if isinstance(content, list) else []:
            if part.get("type") in {"input_text", "text"} and isinstance(part.get("text"), str):
                prompt_parts.append(part["text"])
            elif part.get("type") == "input_image" and isinstance(part.get("image_url"), str):
                images.append(part["image_url"])
            elif part.get("type") == "input_image" and part.get("file_id"):
                raise HTTPException(status_code=400, detail="Local file_id image inputs are not supported; use image_url or a data URL")
    prompt = "\n".join(prompt_parts).strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Responses input must contain image instructions")
    return prompt, images


@app.post("/v1/responses", dependencies=[Depends(require_api_key)])
async def create_response(payload: ResponsesImageRequest, request: Request):
    prompt, input_images = parse_responses_input(payload.input)
    tool = next(tool for tool in payload.tools if tool.get("type") == "image_generation")
    size = image_provider.validate_size(str(tool.get("size", "auto")))
    kwargs = {
        "prompt": prompt,
        "model": str(tool.get("model", "gpt-image-2")),
        "size": size,
        "quality": str(tool.get("quality", "auto")),
        "output_format": str(tool.get("output_format", "png")),
        "background": str(tool.get("background", "auto")),
        "output_compression": tool.get("output_compression"),
        "moderation": str(tool.get("moderation", "auto")),
        "partial_images": int(tool.get("partial_images", 1 if payload.stream else 0)),
        "input_images": input_images,
        "input_image_mask": (tool.get("input_image_mask") or {}).get("image_url"),
        "action": tool.get("action"),
    }
    await refresh_codex_auth()
    response_id = f"resp_{uuid.uuid4().hex}"
    if payload.stream:
        def iterator():
            yield sse({"type": "response.created", "response": {"id": response_id, "object": "response", "status": "in_progress"}})
            try:
                for event in image_provider.stream_generate(**kwargs):
                    if event["type"] == "partial":
                        yield sse({
                            "type": "response.image_generation_call.partial_image",
                            "partial_image_index": event["index"],
                            "partial_image_b64": event["base64_data"],
                            "output_index": 0,
                        })
                    else:
                        generated = event["image"]
                        record_generated_image(generated, prompt)
                        output = {
                            "id": f"ig_{generated.id[4:]}", "type": "image_generation_call",
                            "status": "completed", "result": generated.base64_data,
                            "revised_prompt": generated.revised_prompt,
                        }
                        yield sse({
                            "type": "response.completed",
                            "response": {"id": response_id, "object": "response", "status": "completed", "output": [output], "usage": generated.usage},
                        })
                yield sse("[DONE]")
            except Exception as exc:
                yield sse({"type": "error", **openai_error(str(exc), error_type="api_error")})
        return StreamingResponse(iterator(), media_type="text/event-stream")
    try:
        generated = await generate_one(**kwargs)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    record_generated_image(generated, prompt)
    return {
        "id": response_id,
        "object": "response",
        "created_at": int(time.time()),
        "status": "completed",
        "model": payload.model,
        "output": [{
            "id": f"ig_{generated.id[4:]}", "type": "image_generation_call",
            "status": "completed", "result": generated.base64_data,
            "revised_prompt": generated.revised_prompt,
        }],
        "usage": generated.usage,
    }


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/files/{filename}")
@app.head("/files/{filename}")
async def get_image_file(filename: str) -> FileResponse:
    safe_name = Path(filename).name
    path = settings.image_dir / safe_name
    if safe_name != filename or not path.is_file():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(path)


static_dir = settings.root_dir / "gptlink" / "static"
app.mount("/", StaticFiles(directory=static_dir, html=True), name="dashboard")
