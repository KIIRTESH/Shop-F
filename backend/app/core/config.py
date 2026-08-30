from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AnyHttpUrl, field_validator


class Settings(BaseSettings):
    PROJECT_NAME: str = "FASTSHOP API"
    VERSION: str = "2.0.0"
    API_V1_STR: str = "/api/v1"
    
    # Environment & Debug
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    
    # Database configuration (Defaults to async SQLite for instant zero-config testing; easily switchable to PostgreSQL)
    DATABASE_URL: str = "sqlite+aiosqlite:///./fastshop.db"
    
    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def assemble_db_connection(cls, v: str | None) -> str:
        if not v:
            return "sqlite+aiosqlite:///./fastshop.db"
        # Render PostgreSQL uses postgres:// or postgresql://
        if v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql+asyncpg://", 1)
        if v.startswith("postgresql://") and not v.startswith("postgresql+asyncpg://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v
    
    # In production with PostgreSQL:
    # DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/fastshop"
    
    # CORS Configuration
    CORS_ORIGINS: List[str] = [
        "http://localhost",
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5500",
        "http://127.0.0.1:8000",
        "*"
    ]
    
    # Store Queue Intelligence Configuration
    BASE_ITEM_SCAN_SECONDS: float = 2.5   # Avg time to scan 1 item
    BASE_PAYMENT_SECONDS: float = 20.0     # Avg time for customer payment
    EXPRESS_LANE_MAX_ITEMS: int = 5        # Express limit
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True
    )


settings = Settings()
