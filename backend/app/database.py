"""SQLite database setup with async SQLAlchemy."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

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


async def init_db() -> None:
    """Create all tables on startup and apply SQLite optimisations."""
    from sqlalchemy import text

    from app.models.db_models import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # WAL mode gives better concurrent-read performance and crash
        # durability for local-first SQLite deployments.
        await conn.execute(text("PRAGMA journal_mode=WAL"))
        await conn.execute(text("PRAGMA optimize"))


async def close_db() -> None:
    """Dispose engine on shutdown."""
    await engine.dispose()
