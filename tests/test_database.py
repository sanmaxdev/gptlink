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

