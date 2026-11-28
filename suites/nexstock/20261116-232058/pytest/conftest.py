"""Shared fixture for the generated tests. Made by APIGuard; do not edit."""

from pathlib import Path

import pytest

from apiguard.pytest_support import open_api


@pytest.fixture(scope="session")
def api():
    client = open_api(Path(__file__).resolve().parents[1])
    yield client
    client.close()
