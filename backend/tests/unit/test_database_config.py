from app.database import _engine_connect_args, _is_sqlite_url


def test_sqlite_engine_configuration_is_scoped_to_sqlite() -> None:
    assert _is_sqlite_url("sqlite+aiosqlite:///local.db") is True
    assert _engine_connect_args("sqlite+aiosqlite:///local.db") == {"check_same_thread": False}


def test_postgres_engine_does_not_receive_sqlite_options() -> None:
    url = "postgresql+asyncpg://user:pass@db/documents"

    assert _is_sqlite_url(url) is False
    assert _engine_connect_args(url) == {}
