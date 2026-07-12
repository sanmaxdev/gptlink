from pathlib import Path

import pytest

from gptlink.agent_service import AgentImageService
from gptlink.config import Settings


def test_local_references_are_restricted_to_allowed_roots(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    reference = allowed / "reference.png"
    reference.write_bytes(b"not-a-real-png")
    settings = Settings(
        root_dir=tmp_path,
        data_dir=tmp_path / "data",
        image_dir=tmp_path / "data" / "images",
        database_path=tmp_path / "data" / "gptlink.db",
        codex_home=tmp_path / "codex",
        hermes_home=tmp_path / "hermes",
        host="127.0.0.1",
        port=8787,
        public_base_url="http://127.0.0.1:8787",
        mcp_allowed_roots=(allowed,),
    )
    service = AgentImageService(settings)

    assert service._safe_local_path(str(reference), must_exist=True) == reference.resolve()
    with pytest.raises(ValueError, match="outside GPTLink's allowed roots"):
        service._safe_local_path(str(tmp_path.parent / "secret.png"), must_exist=False)


def test_capabilities_advertise_agent_controls(tmp_path: Path) -> None:
    capabilities = AgentImageService().capabilities()

    assert capabilities["editing"] is True
    assert capabilities["reference_images"]["maximum"] == 16
    assert capabilities["outputs_per_call"]["maximum"] == 10
