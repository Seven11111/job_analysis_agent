from pathlib import Path

import pytest

from src.config import Settings


@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    return Settings(database_path=str(tmp_path / "test.db"))
