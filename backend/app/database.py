"""SQLite database setup with async SQLAlchemy.

Tables are created and migrated by Alembic (``alembic upgrade head``)
when the project is configured for production. For first-run dev mode
or for environments that have not adopted Alembic yet, ``init_db``
still falls back to ``Base.metadata.create_all`` so a fresh checkout
keeps working.

Migrating from v0.2.x
---------------------

If you have an existing ``extraction.db`` from v0.2.x, run::

    alembic stamp head

That records the current schema as the latest revision without trying
to recreate any tables. New deployments go through the normal
``alembic upgrade head`` path.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

logger = logging.getLogger(__name__)

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    connect_args={"check_same_thread": False},
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncSession:  # type: ignore[misc]
    """FastAPI dependency that yields an async DB session."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def _alembic_upgrade_head() -> bool:
    """Best-effort ``alembic upgrade head`` at startup.

    Returns True if alembic ran, False if it was skipped (alembic not
    installed, no migration directory, or ``SKIP_ALEMBIC=1``). We
    never raise from here — schema creation falls back to
    ``Base.metadata.create_all`` if alembic is not available.
    """
    if os.environ.get("SKIP_ALEMBIC") == "1":
        return False
    try:
        from alembic import command
        from alembic.config import Config
    except ImportError:
        return False

    repo_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(repo_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(repo_root / "backend" / "alembic"))
    try:
        await asyncio.to_thread(command.upgrade, cfg, "head")
    except Exception as exc:
        logger.warning("alembic.upgrade_failed: %s", exc)
        return False
    return True


async def init_db() -> None:
    """Create all tables on startup and apply SQLite optimisations.

    Tries Alembic first; falls back to ``Base.metadata.create_all`` for
    legacy/dev mode. Either way, WAL mode and ``PRAGMA optimize`` are
    applied unconditionally.
    """
    from sqlalchemy import text

    from app.models.db_models import Base

    ran_alembic = await _alembic_upgrade_head()
    if not ran_alembic:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async with engine.begin() as conn:
        await conn.execute(text("PRAGMA journal_mode=WAL"))
        await conn.execute(text("PRAGMA optimize"))


async def close_db() -> None:
    """Dispose engine on shutdown."""
    await engine.dispose()


# Late import for asyncio.to_thread; the module is hot-loaded.
import asyncio  # noqa: E402
