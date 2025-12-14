"""Application configuration using Pydantic settings."""

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database - SQLAlchemy (asyncpg)
    database_url: str = Field(
        ...,
        description="SQLAlchemy connection string (postgresql+asyncpg://...)",
    )

    # Database - Procrastinate (psycopg)
    procrastinate_database_url: str = Field(
        ...,
        description="Procrastinate connection string (postgresql://...)",
    )

    # GitHub App
    github_app_id: int = Field(..., description="GitHub App ID")
    github_app_private_key: str = Field(
        ...,
        description="GitHub App private key (PEM format)",
    )
    github_webhook_secret: str = Field(
        ...,
        description="Webhook secret for signature verification",
    )

    # Claude API
    anthropic_api_key: str = Field(..., description="Anthropic API key")
    default_model: str = Field(
        "claude-sonnet-4-20250514",
        description="Default Claude model",
    )
    max_tokens_per_review: int = Field(
        4096,
        description="Max output tokens per review",
    )

    # Cost tracking (Claude pricing in cents per 1M tokens)
    input_token_cost_per_million: int = Field(
        300,
        description="Input cost in cents per 1M tokens",
    )
    output_token_cost_per_million: int = Field(
        1500,
        description="Output cost in cents per 1M tokens",
    )

    # Defaults
    default_monthly_budget_cents: int = Field(
        10000,
        description="Default monthly budget ($100)",
    )
    max_files_per_review: int = Field(
        50,
        description="Skip PRs with more files than this",
    )
    max_diff_size_bytes: int = Field(
        500000,
        description="Skip diffs larger than 500KB",
    )

    # Server
    host: str = Field("0.0.0.0")
    port: int = Field(8000)
    log_level: str = Field("INFO")

    # Feature flags
    enable_line_comments: bool = Field(
        True,
        description="Post line-level comments vs summary only",
    )

    # Debounce settings
    review_debounce_seconds: int = Field(
        30,
        description="Wait this long before processing a PR review to debounce rapid commits",
    )

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
