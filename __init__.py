"""GPTLink Hermes plugin registration."""

from pathlib import Path

try:
    from .hermes_plugin import schemas, tools
except ImportError:  # Direct source loading without a package namespace.
    from hermes_plugin import schemas, tools


def register(ctx) -> None:
    """Register GPTLink tools and its bundled workflow skill."""
    ctx.register_tool(
        name="gptlink_manage",
        toolset="gptlink",
        schema=schemas.MANAGE,
        handler=tools.manage,
        description="Install, authenticate, start, update, or diagnose GPTLink.",
    )
    ctx.register_tool(
        name="gptlink_generate",
        toolset="gptlink",
        schema=schemas.GENERATE,
        handler=tools.generate,
        description="Generate or edit images through the managed GPTLink service.",
    )
    skill = Path(__file__).parent / "skills" / "gptlink-image" / "SKILL.md"
    if skill.exists():
        ctx.register_skill("gptlink-image", skill)
