import tomllib
from pathlib import Path

from app.config import Settings


def test_release_versions_are_consistent() -> None:
    root = Path(__file__).parents[1]
    version = (root / "VERSION").read_text().strip()
    with (root / "pyproject.toml").open("rb") as project_file:
        project_version = tomllib.load(project_file)["project"]["version"]

    assert version == project_version
    assert version == Settings.model_fields["app_version"].default
