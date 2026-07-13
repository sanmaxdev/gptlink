from pathlib import Path

from gptlink.config import Settings
from gptlink.jobs import JobManager


def job_settings(tmp_path: Path) -> Settings:
    return Settings(
        root_dir=tmp_path,
        data_dir=tmp_path / "data",
        image_dir=tmp_path / "data" / "images",
        database_path=tmp_path / "data" / "gptlink.db",
        codex_home=tmp_path / "codex",
        hermes_home=tmp_path / "hermes",
        host="127.0.0.1",
        port=8787,
        public_base_url="http://127.0.0.1:8787",
        mcp_allowed_roots=(),
    )


def test_worker_completes_persisted_job_and_redacts_inputs(monkeypatch, tmp_path: Path) -> None:
    manager = JobManager(job_settings(tmp_path))
    manager.settings.ensure_directories()
    manager.database.initialize()
    manager.database.create_job(
        job_id="job_worker",
        operation="edit",
        request={
            "prompt": "Edit the reference",
            "reference_images": ["data:image/png;base64,aGVsbG8="],
            "mask_image": "data:image/png;base64,bWFzaw==",
        },
        webhook_url=None,
        metadata={},
    )

    class FakeImageService:
        def __init__(self, _settings) -> None:
            pass

        async def generate(self, **kwargs):
            assert kwargs["action"] == "edit"
            return {"state": "completed", "images": [{"url": "/files/test.png"}]}

    monkeypatch.setattr("gptlink.jobs.AgentImageService", FakeImageService)

    assert manager._process_job() is True
    job = manager.get_job("job_worker")
    assert job is not None
    assert job["status"] == "completed"
    assert job["result"]["images"][0]["url"] == "/files/test.png"
    assert job["request"]["reference_image_count"] == 1
    assert "reference_images" not in job["request"]
    assert "mask_image" not in job["request"]
