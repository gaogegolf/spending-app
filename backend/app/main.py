"""Main FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings

# Create FastAPI application
app = FastAPI(
    title="Personal Finance Manager API",
    description="API for managing personal finance transactions with automatic classification",
    version="1.0.0",
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
from app.api.v1 import accounts, imports, transactions, stats, merchant_categories, rules

app.include_router(accounts.router, prefix="/api/v1", tags=["accounts"])
app.include_router(imports.router, prefix="/api/v1", tags=["imports"])
app.include_router(transactions.router, prefix="/api/v1", tags=["transactions"])
app.include_router(stats.router, prefix="/api/v1", tags=["stats"])
app.include_router(merchant_categories.router, prefix="/api/v1", tags=["merchant-categories"])
app.include_router(rules.router, prefix="/api/v1", tags=["rules"])
