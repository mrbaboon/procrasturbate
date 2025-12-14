"""Database connection and session management."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .config import settings

# Create async engine
async_engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
)

# Session factory
async_session_factory = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for FastAPI to get a database session."""
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db() -> None:
    """Initialize database connection (called on startup)."""
    # Just verify connection works
    async with async_engine.begin() as conn:
        await conn.run_sync(lambda _: None)
