"""Model-visible tool schemas for the GPTLink Hermes plugin."""

MANAGE = {
    "name": "gptlink_manage",
    "description": (
        "Manage the local GPTLink image API. Use setup before the first image request; "
        "it reuses existing Hermes/Codex authentication or returns a device-login URL and code. "
        "Use auth_complete after the user approves that code."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["setup", "auth_complete", "ensure", "status", "restart", "update", "rotate_key", "logs"],
                "description": "Lifecycle operation to perform.",
            }
        },
        "required": ["action"],
    },
}

GENERATE = {
    "name": "gptlink_generate",
    "description": (
        "Generate an image or edit up to 16 local reference images with GPTLink. "
        "Returns an absolute image path suitable for native Telegram, Discord, or CLI delivery."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "prompt": {"type": "string", "description": "Complete image instructions."},
            "aspect_ratio": {
                "type": "string",
                "description": "Output ratio such as 1:1, 16:9, 9:16, 4:3, or 3:2.",
                "default": "1:1",
            },
            "quality": {
                "type": "string", "enum": ["auto", "low", "medium", "high"], "default": "auto"
            },
            "format": {
                "type": "string", "enum": ["png", "jpeg", "webp"], "default": "png"
            },
            "reference_paths": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 16,
                "description": "Absolute local paths of reference images.",
            },
        },
        "required": ["prompt"],
    },
}

