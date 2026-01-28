"""Main FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from alembic.config import Config
from alembic import command

from app.config import settings

logger = logging.getLogger(__name__)


def run_migrations():
    """Run alembic migrations on startup if needed."""
    from alembic.runtime.migration import MigrationContext
    from sqlalchemy import create_engine, text

    try:
        # Check current revision
        engine = create_engine(settings.DATABASE_URL)
        with engine.connect() as conn:
            context = MigrationContext.configure(conn)
            current_rev = context.get_current_revision()

        # Get head revision
        alembic_cfg = Config("alembic.ini")
        from alembic.script import ScriptDirectory
        script = ScriptDirectory.from_config(alembic_cfg)
        head_rev = script.get_current_head()

        if current_rev == head_rev:
            logger.debug("Database schema is up to date")
            return

        # Run migrations
        logger.info(f"Running migrations: {current_rev} -> {head_rev}")
        command.upgrade(alembic_cfg, "head")
        logger.info("Database migrations completed successfully")
    except Exception as e:
        logger.error(f"Failed to run migrations: {e}")
        raise


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - run migrations on startup."""
    run_migrations()
    yield


# Create FastAPI application
app = FastAPI(
    title="Personal Finance Manager API",
    description="API for managing personal finance transactions with automatic classification",
    version="1.0.0",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """Root endpoint - health check."""
    return {
        "status": "ok",
        "message": "Personal Finance Manager API",
        "version": "1.0.0",
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


# Import and include API routers
from app.api.v1 import accounts, imports, transactions, stats, merchant_categories, rules, brokerage, reports, auth, backup

app.include_router(auth.router, prefix="/api/v1", tags=["auth"])
app.include_router(accounts.router, prefix="/api/v1", tags=["accounts"])
app.include_router(imports.router, prefix="/api/v1", tags=["imports"])
app.include_router(transactions.router, prefix="/api/v1", tags=["transactions"])
app.include_router(stats.router, prefix="/api/v1", tags=["stats"])
app.include_router(merchant_categories.router, prefix="/api/v1", tags=["merchant-categories"])
app.include_router(rules.router, prefix="/api/v1", tags=["rules"])
app.include_router(brokerage.router, prefix="/api/v1", tags=["brokerage"])
app.include_router(reports.router, prefix="/api/v1", tags=["reports"])
app.include_router(backup.router, prefix="/api/v1", tags=["backup"])
