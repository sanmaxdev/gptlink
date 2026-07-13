from pathlib import Path

from gptlink.database import Database


def test_api_key_can_be_created_validated_and_revoked(tmp_path: Path) -> None:
    database = Database(tmp_path / "test.db")
    database.initialize()
    created = database.create_api_key("Test")

    assert created.secret.startswith("gptlink_")
    assert database.validate_api_key(created.secret)
    assert database.revoke_api_key(created.id)
    assert not database.validate_api_key(created.secret)


def test_persistent_job_lifecycle_and_cancellation(tmp_path: Path) -> None:
    database = Database(tmp_path / "test.db")
    database.initialize()
    first = database.create_job(
        job_id="job_first",
        operation="generate",
        request={"prompt": "First"},
        webhook_url=None,
        metadata={"project": "test"},
    )
    database.create_job(
        job_id="job_second",
        operation="generate",
        request={"prompt": "Second"},
        webhook_url=None,
        metadata={},
    )

    assert first["status"] == "queued"
    claimed = database.claim_next_job()
    assert claimed is not None
    assert claimed["id"] == "job_first"
    completed = database.finish_job("job_first", result={"images": []})
    assert completed is not None
    assert completed["status"] == "completed"
    assert completed["result"] == {"images": []}
    cancelled = database.cancel_job("job_second")
    assert cancelled is not None
    assert cancelled["status"] == "cancelled"
