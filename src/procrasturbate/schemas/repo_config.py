"""Schema for .aireviewer.yaml configuration files."""

from typing import Literal

from pydantic import BaseModel, Field


class PathConfig(BaseModel):
    """Path include/exclude patterns."""

    include: list[str] = Field(default_factory=lambda: ["**/*"])
    exclude: list[str] = Field(default_factory=list)


class RulesConfig(BaseModel):
    """Review rules configuration."""

    security: bool = True
    performance: bool = True
    style: bool = True
    bugs: bool = True
    documentation: bool = False

    # Custom rule sets (keys are rule names, values are descriptions/prompts)
    custom: dict[str, str] = Field(default_factory=dict)


class ReviewConfig(BaseModel):
    """Schema for .aireviewer.yaml files."""

    # Paths
    paths: PathConfig = Field(default_factory=PathConfig)

    # Rules
    rules: RulesConfig = Field(default_factory=RulesConfig)

    # Behavior
    auto_review: bool = True
    review_on: list[Literal["opened", "synchronize", "reopened"]] = Field(
        default_factory=lambda: ["opened", "synchronize"]
    )

    # Limits
    max_files: int = Field(50, ge=1, le=200)

    # Context - files to include in prompt for repo-specific knowledge
    context_files: list[str] = Field(default_factory=list)

    # Model override (null = use default)
    model: str | None = None

    # Language/framework hints for better reviews
    languages: list[str] = Field(default_factory=list)  # e.g., ["python", "typescript"]
    frameworks: list[str] = Field(default_factory=list)  # e.g., ["django", "react"]

    # Prompt additions
    additional_instructions: str | None = None

    @classmethod
    def get_default(cls) -> "ReviewConfig":
        """Return default configuration."""
        return cls()
