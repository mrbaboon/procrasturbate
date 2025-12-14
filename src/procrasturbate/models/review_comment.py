"""Review comment model."""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .review import Review


class CommentSeverity(str, Enum):
    """Severity level of a review comment."""

    CRITICAL = "critical"
    WARNING = "warning"
    SUGGESTION = "suggestion"
    NITPICK = "nitpick"
    PRAISE = "praise"  # For positive feedback


class ReviewComment(Base):
    """Individual line-level comments within a review."""

    __tablename__ = "review_comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    review_id: Mapped[int] = mapped_column(
        ForeignKey("reviews.id", ondelete="CASCADE"),
        index=True,
    )

    # Location
    file_path: Mapped[str] = mapped_column(String(500))
    line_number: Mapped[int] = mapped_column(Integer)  # Line in the file
    diff_position: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )  # Position in diff (for GitHub API)

    # Content
    severity: Mapped[CommentSeverity] = mapped_column(SQLEnum(CommentSeverity))
    category: Mapped[str] = mapped_column(
        String(50),
    )  # security, performance, style, bug, etc.
    message: Mapped[str] = mapped_column(Text)
    suggested_fix: Mapped[str | None] = mapped_column(Text, nullable=True)

    # GitHub tracking
    github_comment_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    # Relationships
    review: Mapped["Review"] = relationship(back_populates="comments")
