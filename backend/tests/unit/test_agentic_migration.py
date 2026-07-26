import importlib.util
from pathlib import Path


def _migration_module():
    path = Path(__file__).parents[2] / "alembic" / "versions" / "0006_agentic_page_checkpoints.py"
    spec = importlib.util.spec_from_file_location("agentic_checkpoint_migration", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_agentic_checkpoint_migration_upgrade_and_downgrade_are_symmetric(monkeypatch) -> None:
    migration = _migration_module()
    added: list[str] = []
    dropped: list[str] = []
    monkeypatch.setattr(migration.op, "add_column", lambda table, column: added.append(column.name))
    monkeypatch.setattr(migration.op, "drop_column", lambda table, column: dropped.append(column))

    migration.upgrade()
    migration.downgrade()

    assert set(added) == set(dropped)
    assert {"state_path", "fingerprint", "quality_status", "repair_count"} <= set(added)
