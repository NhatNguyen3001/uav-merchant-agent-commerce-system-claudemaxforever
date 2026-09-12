import pytest

from macs.seeddata import load_seed
from macs.store import MemoryStore


@pytest.fixture
def seeded_store():
    return load_seed(MemoryStore())
