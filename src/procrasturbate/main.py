"""FastAPI application entrypoint."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .api.router import router
from .config import settings
from .database import init_db
from .utils.logging import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    setup_logging()
    await init_db()
    yield
    # Shutdown
    pass


app = FastAPI(
    title="Procrasturbate",
    description="The AI PR reviewer that does the work while you procrastinate",
    version="0.1.0",
    lifespan=lifespan,
)

# Mount static files if directory exists
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Include routes
app.include_router(router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "procrasturbate.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
