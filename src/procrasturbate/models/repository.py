"""Repository model."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .installation import Installation
    from .review import Review


class Repository(Base):
    """Per-repo configuration and limits."""

    __tablename__ = "repositories"

    id: Mapped[int] = mapped_column(primary_key=True)
    installation_id: Mapped[int] = mapped_column(
        ForeignKey("installations.id", ondelete="CASCADE"),
        index=True,
    )

    github_repo_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255), index=True)  # "owner/repo"
    default_branch: Mapped[str] = mapped_column(String(255), default="main")

    # Feature flags
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_review: Mapped[bool] = mapped_column(Boolean, default=True)

    # Per-repo budget override (null = use installation budget)
    monthly_budget_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Cached config from .aireviewer.yaml (refreshed on each PR)
    config_yaml: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    config_fetched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    installation: Mapped["Installation"] = relationship(back_populates="repositories")
    reviews: Mapped[list["Review"]] = relationship(
        back_populates="repository",
        cascade="all, delete-orphan",
    )
