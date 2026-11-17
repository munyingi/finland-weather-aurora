from datetime import datetime

import pytest

from ingest import storage
from ingest.demo import DemoClient

NOW = datetime(2026, 11, 17, 18, 30)


@pytest.fixture
def now() -> datetime:
    return NOW


@pytest.fixture
def demo_client(now) -> DemoClient:
    return DemoClient(now)


@pytest.fixture
def con(tmp_path):
    c = storage.connect(tmp_path / "test.duckdb")
    yield c
    c.close()
