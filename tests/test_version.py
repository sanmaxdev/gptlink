from pathlib import Path

from gptlink import __version__
from gptlink.main import app


def test_public_versions_stay_in_sync() -> None:
    plugin_manifest = (Path(__file__).parents[1] / "plugin.yaml").read_text(
        encoding="utf-8"
    )

    assert __version__ == "0.5.0"
    assert app.version == __version__
    assert f"version: {__version__}" in plugin_manifest
