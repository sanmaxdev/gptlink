from gptlink.mcp_server import create_mcp_server


def test_mcp_exposes_complete_image_toolset() -> None:
    server = create_mcp_server(require_auth=False)
    tools = {tool.name for tool in server._tool_manager.list_tools()}

    assert tools == {
        "gptlink_status",
        "gptlink_models",
        "gptlink_generate",
        "gptlink_edit",
        "gptlink_variation",
        "gptlink_history",
    }


def test_remote_mcp_requires_token_verifier() -> None:
    server = create_mcp_server(require_auth=True)

    assert server._token_verifier is not None
    assert server.settings.stateless_http is True
