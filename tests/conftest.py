import os
from pathlib import Path
from tempfile import gettempdir

import pytest


# Ensure test collection/import (including app module import-time init_storage)
# never touches the real runtime DB under data/.
_GLOBAL_TEST_DB = Path(gettempdir()) / "stockanalysiskit_pytest_global.db"
os.environ["STOCKANALYSISKIT_DB_PATH"] = str(_GLOBAL_TEST_DB)


@pytest.fixture(autouse=True)
def isolate_sqlite_db_per_test(monkeypatch, tmp_path):
    db_path = tmp_path / "stockanalysiskit.db"
    monkeypatch.setenv("STOCKANALYSISKIT_DB_PATH", str(db_path))

    # Reset init cache so each test can initialize its isolated DB path cleanly.
    import persistence

    persistence._INITIALIZED_DB_PATHS.clear()
    yield
