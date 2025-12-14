"""Review model."""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .repository import Repository
    from .review_comment import ReviewComment


class ReviewStatus(str, Enum):
    """Status of a review."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"  # e.g., budget exceeded, too many files
    SUPERSEDED = "superseded"  # newer commit arrived, cancelled to save cost


class ReviewTrigger(str, Enum):
    """What triggered the review."""

    PR_OPENED = "pr_opened"
    PR_SYNCHRONIZE = "pr_synchronize"
    PR_REOPENED = "pr_reopened"
    COMMAND = "command"  # @reviewer review


class Review(Base):
    """A single PR review."""

    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    repository_id: Mapped[int] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE"),
        index=True,
    )

    # PR info
    pr_number: Mapped[int] = mapped_column(Integer, index=True)
    pr_title: Mapped[str] = mapped_column(String(500))
    pr_author: Mapped[str] = mapped_column(String(255))
    head_sha: Mapped[str] = mapped_column(String(40), index=True)
    base_sha: Mapped[str] = mapped_column(String(40))

    # Review state
    status: Mapped[ReviewStatus] = mapped_column(
        SQLEnum(ReviewStatus),
        default=ReviewStatus.PENDING,
        index=True,
    )
    trigger: Mapped[ReviewTrigger] = mapped_column(SQLEnum(ReviewTrigger))
    triggered_by: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )  # GitHub username if command

    # Results
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_level: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )  # low, medium, high, critical
    github_review_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )  # GitHub's review ID
    github_check_run_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )  # GitHub Check Run ID for status indication

    # Stats
    files_reviewed: Mapped[int] = mapped_column(Integer, default=0)
    comments_posted: Mapped[int] = mapped_column(Integer, default=0)

    # Cost tracking
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_cents: Mapped[int] = mapped_column(Integer, default=0)

    # Error info if failed
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Config snapshot (what config was active at review time)
    config_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    repository: Mapped["Repository"] = relationship(back_populates="reviews")
    comments: Mapped[list["ReviewComment"]] = relationship(
        back_populates="review",
        cascade="all, delete-orphan",
    )
