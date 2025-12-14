"""GitHub App installation model."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .repository import Repository
    from .usage import UsageRecord


class Installation(Base):
    """Represents a GitHub App installation (org or user account)."""

    __tablename__ = "installations"

    id: Mapped[int] = mapped_column(primary_key=True)
    github_installation_id: Mapped[int] = mapped_column(
        BigInteger,
        unique=True,
        index=True,
    )

    # Owner info (org or user)
    owner_type: Mapped[str] = mapped_column(String(20))  # "Organization" or "User"
    owner_login: Mapped[str] = mapped_column(String(255), index=True)
    owner_github_id: Mapped[int] = mapped_column(BigInteger)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    suspended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Cost limits (monthly, in USD cents to avoid float issues)
    monthly_budget_cents: Mapped[int] = mapped_column(default=10000)  # $100 default

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
    repositories: Mapped[list["Repository"]] = relationship(
        back_populates="installation",
        cascade="all, delete-orphan",
    )
    usage_records: Mapped[list["UsageRecord"]] = relationship(
        back_populates="installation",
        cascade="all, delete-orphan",
    )
