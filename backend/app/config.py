"""Application configuration management."""

from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    DATABASE_URL: str = "sqlite:///./spending_app.db"

    # API Keys
    ANTHROPIC_API_KEY: str = ""

    # Security
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://localhost:8000"

    # JWT Authentication
    JWT_SECRET_KEY: str = "jwt-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # File Upload
    MAX_FILE_SIZE_MB: int = 10
    UPLOAD_DIR: str = "./uploads"

    # Feature Flags
    ENABLE_PDF_PARSING: bool = True
    ENABLE_LLM_CLASSIFICATION: bool = True
    ENABLE_LLM_PDF_EXTRACTION: bool = True  # Enable Claude Vision fallback for unknown PDF formats
    ENABLE_FX_CONVERSION: bool = True

    # FX Rate API (using Frankfurter - free, no API key required)
    FX_RATE_API_URL: str = "https://api.frankfurter.app"

    # Environment
    ENVIRONMENT: str = "development"

    @property
    def allowed_origins_list(self) -> List[str]:
        """Parse ALLOWED_ORIGINS into a list."""
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",")]

    @property
    def max_file_size_bytes(self) -> int:
        """Convert max file size from MB to bytes."""
        return self.MAX_FILE_SIZE_MB * 1024 * 1024

    class Config:
        env_file = ".env"
        case_sensitive = True


# Global settings instance
settings = Settings()
