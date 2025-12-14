# Procrasturbate 🍆 - Technical Specification

*The AI PR reviewer that does the work while you procrastinate*

## Overview

A self-hosted, configurable AI-powered pull request reviewer that integrates with GitHub. Provides automated code reviews with line-level comments, supports per-repo configuration, enforces cost limits, and responds to commands via PR comments.

**Stack:**
- FastAPI (async)
- SQLAlchemy 2.0 (async) + PostgreSQL 15+
- Procrastinate (PostgreSQL-backed task queue)
- httpx (async HTTP client)
- Pydantic v2 (settings, validation)

---

## Project Structure

```
procrasturbate/
├── alembic/
│   ├── versions/
│   ├── env.py
│   └── alembic.ini
├── src/
│   └── procrasturbate/
│       ├── __init__.py
│       ├── main.py                 # FastAPI app entrypoint
│       ├── config.py               # Pydantic settings
│       ├── database.py             # SQLAlchemy async engine/session
│       ├── models/
│       │   ├── __init__.py
│       │   ├── base.py             # DeclarativeBase
│       │   ├── installation.py     # GitHub App installations (orgs/users)
│       │   ├── repository.py       # Repository config + limits
│       │   ├── review.py           # Review records
│       │   ├── review_comment.py   # Individual line comments
│       │   └── usage.py            # Token usage tracking
│       ├── schemas/
│       │   ├── __init__.py
│       │   ├── github_webhooks.py  # Pydantic models for webhook payloads
│       │   ├── repo_config.py      # .aireviewer.yaml schema
│       │   ├── review.py           # Review request/response schemas
│       │   └── admin.py            # Admin API schemas
│       ├── api/
│       │   ├── __init__.py
│       │   ├── router.py           # Main router aggregation
│       │   ├── webhooks.py         # GitHub webhook endpoints
│       │   ├── admin.py            # Admin/dashboard endpoints
│       │   └── health.py           # Health check endpoints
│       ├── services/
│       │   ├── __init__.py
│       │   ├── github_client.py    # GitHub API wrapper
│       │   ├── claude_client.py    # Claude API wrapper
│       │   ├── config_loader.py    # Fetch/parse repo config
│       │   ├── diff_parser.py      # Parse unified diffs, map line positions
│       │   ├── review_engine.py    # Orchestrates the review process
│       │   ├── cost_tracker.py     # Token counting, limit enforcement
│       │   └── comment_commands.py # Parse and handle @reviewer commands
│       ├── tasks/
│       │   ├── __init__.py
│       │   ├── worker.py           # Procrastinate app setup
│       │   ├── review_tasks.py     # Review job definitions
│       │   └── cleanup_tasks.py    # Periodic cleanup jobs
│       └── utils/
│           ├── __init__.py
│           ├── github_auth.py      # JWT generation, installation tokens
│           └── logging.py          # Structured logging setup
├── tests/
│   ├── conftest.py
│   ├── test_diff_parser.py
│   ├── test_webhook_handlers.py
│   ├── test_review_engine.py
│   └── fixtures/
│       ├── sample_diffs/
│       └── webhook_payloads/
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml
├── pyproject.toml
├── README.md
└── .env.example
```

---

## Database Models

### Installation

Represents a GitHub App installation (org or user account).

```python
# src/procrasturbate/models/installation.py

from datetime import datetime
from sqlalchemy import BigInteger, String, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base

class Installation(Base):
    __tablename__ = "installations"

    id: Mapped[int] = mapped_column(primary_key=True)
    github_installation_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    
    # Owner info (org or user)
    owner_type: Mapped[str] = mapped_column(String(20))  # "Organization" or "User"
    owner_login: Mapped[str] = mapped_column(String(255), index=True)
    owner_github_id: Mapped[int] = mapped_column(BigInteger)
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Cost limits (monthly, in USD cents to avoid float issues)
    monthly_budget_cents: Mapped[int] = mapped_column(default=10000)  # $100 default
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    repositories: Mapped[list["Repository"]] = relationship(back_populates="installation", cascade="all, delete-orphan")
    usage_records: Mapped[list["UsageRecord"]] = relationship(back_populates="installation", cascade="all, delete-orphan")
```

### Repository

Per-repo configuration and limits.

```python
# src/procrasturbate/models/repository.py

from datetime import datetime
from sqlalchemy import BigInteger, String, Boolean, Integer, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB
from .base import Base

class Repository(Base):
    __tablename__ = "repositories"

    id: Mapped[int] = mapped_column(primary_key=True)
    installation_id: Mapped[int] = mapped_column(ForeignKey("installations.id", ondelete="CASCADE"), index=True)
    
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
    config_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    installation: Mapped["Installation"] = relationship(back_populates="repositories")
    reviews: Mapped[list["Review"]] = relationship(back_populates="repository", cascade="all, delete-orphan")
```

### Review

A single PR review.

```python
# src/procrasturbate/models/review.py

from datetime import datetime
from enum import Enum
from sqlalchemy import BigInteger, String, Integer, DateTime, ForeignKey, Text, func, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB
from .base import Base

class ReviewStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"  # e.g., budget exceeded, too many files

class ReviewTrigger(str, Enum):
    PR_OPENED = "pr_opened"
    PR_SYNCHRONIZE = "pr_synchronize"
    PR_REOPENED = "pr_reopened"
    COMMAND = "command"  # @reviewer review

class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id", ondelete="CASCADE"), index=True)
    
    # PR info
    pr_number: Mapped[int] = mapped_column(Integer, index=True)
    pr_title: Mapped[str] = mapped_column(String(500))
    pr_author: Mapped[str] = mapped_column(String(255))
    head_sha: Mapped[str] = mapped_column(String(40), index=True)
    base_sha: Mapped[str] = mapped_column(String(40))
    
    # Review state
    status: Mapped[ReviewStatus] = mapped_column(SQLEnum(ReviewStatus), default=ReviewStatus.PENDING, index=True)
    trigger: Mapped[ReviewTrigger] = mapped_column(SQLEnum(ReviewTrigger))
    triggered_by: Mapped[str | None] = mapped_column(String(255), nullable=True)  # GitHub username if command
    
    # Results
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_level: Mapped[str | None] = mapped_column(String(20), nullable=True)  # low, medium, high, critical
    github_review_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)  # GitHub's review ID
    
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    repository: Mapped["Repository"] = relationship(back_populates="reviews")
    comments: Mapped[list["ReviewComment"]] = relationship(back_populates="review", cascade="all, delete-orphan")
```

### ReviewComment

Individual line-level comments within a review.

```python
# src/procrasturbate/models/review_comment.py

from datetime import datetime
from enum import Enum
from sqlalchemy import String, Integer, DateTime, ForeignKey, Text, func, Enum as SQLEnum, BigInteger
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base

class CommentSeverity(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    SUGGESTION = "suggestion"
    NITPICK = "nitpick"
    PRAISE = "praise"  # For positive feedback

class ReviewComment(Base):
    __tablename__ = "review_comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    review_id: Mapped[int] = mapped_column(ForeignKey("reviews.id", ondelete="CASCADE"), index=True)
    
    # Location
    file_path: Mapped[str] = mapped_column(String(500))
    line_number: Mapped[int] = mapped_column(Integer)  # Line in the file
    diff_position: Mapped[int | None] = mapped_column(Integer, nullable=True)  # Position in diff (for GitHub API)
    
    # Content
    severity: Mapped[CommentSeverity] = mapped_column(SQLEnum(CommentSeverity))
    category: Mapped[str] = mapped_column(String(50))  # security, performance, style, bug, etc.
    message: Mapped[str] = mapped_column(Text)
    suggested_fix: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # GitHub tracking
    github_comment_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    review: Mapped["Review"] = relationship(back_populates="comments")
```

### UsageRecord

Monthly token/cost tracking per installation.

```python
# src/procrasturbate/models/usage.py

from datetime import datetime
from sqlalchemy import Integer, DateTime, ForeignKey, func, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base

class UsageRecord(Base):
    __tablename__ = "usage_records"
    __table_args__ = (
        UniqueConstraint("installation_id", "year", "month", name="uq_installation_year_month"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    installation_id: Mapped[int] = mapped_column(ForeignKey("installations.id", ondelete="CASCADE"), index=True)
    
    # Period
    year: Mapped[int] = mapped_column(Integer)
    month: Mapped[int] = mapped_column(Integer)  # 1-12
    
    # Totals
    total_input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_cost_cents: Mapped[int] = mapped_column(Integer, default=0)
    total_reviews: Mapped[int] = mapped_column(Integer, default=0)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    installation: Mapped["Installation"] = relationship(back_populates="usage_records")
```

---

## Configuration Schema

### Application Settings

```python
# src/procrasturbate/config.py

from pydantic_settings import BaseSettings
from pydantic import Field

class Settings(BaseSettings):
    # Database
    database_url: str = Field(..., description="PostgreSQL connection string")
    
    # GitHub App
    github_app_id: int = Field(..., description="GitHub App ID")
    github_app_private_key: str = Field(..., description="GitHub App private key (PEM format)")
    github_webhook_secret: str = Field(..., description="Webhook secret for signature verification")
    
    # Claude API
    anthropic_api_key: str = Field(..., description="Anthropic API key")
    default_model: str = Field("claude-sonnet-4-20250514", description="Default Claude model")
    max_tokens_per_review: int = Field(4096, description="Max output tokens per review")
    
    # Cost tracking (Claude pricing in cents per 1M tokens)
    # Update these as pricing changes
    input_token_cost_per_million: int = Field(300, description="Input cost in cents per 1M tokens")
    output_token_cost_per_million: int = Field(1500, description="Output cost in cents per 1M tokens")
    
    # Defaults
    default_monthly_budget_cents: int = Field(10000, description="Default monthly budget ($100)")
    max_files_per_review: int = Field(50, description="Skip PRs with more files than this")
    max_diff_size_bytes: int = Field(500000, description="Skip diffs larger than 500KB")
    
    # Server
    host: str = Field("0.0.0.0")
    port: int = Field(8000)
    log_level: str = Field("INFO")
    
    # Feature flags
    enable_line_comments: bool = Field(True, description="Post line-level comments vs summary only")
    
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
```

### Repository Config Schema (.aireviewer.yaml)

```python
# src/procrasturbate/schemas/repo_config.py

from pydantic import BaseModel, Field
from typing import Literal

class PathConfig(BaseModel):
    include: list[str] = Field(default_factory=lambda: ["**/*"])
    exclude: list[str] = Field(default_factory=list)

class RulesConfig(BaseModel):
    security: bool = True
    performance: bool = True
    style: bool = True
    bugs: bool = True
    documentation: bool = False
    
    # Custom rule sets (keys are rule names, values are descriptions/prompts)
    custom: dict[str, str] = Field(default_factory=dict)

class ReviewConfig(BaseModel):
    """Schema for .aireviewer.yaml files"""
    
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
        return cls()
```

---

## GitHub Webhook Schemas

```python
# src/procrasturbate/schemas/github_webhooks.py

from pydantic import BaseModel, Field
from typing import Literal

class GitHubUser(BaseModel):
    login: str
    id: int

class GitHubRepository(BaseModel):
    id: int
    full_name: str
    name: str
    default_branch: str = "main"
    private: bool

class GitHubInstallation(BaseModel):
    id: int
    account: GitHubUser

class PullRequestHead(BaseModel):
    sha: str
    ref: str

class PullRequestBase(BaseModel):
    sha: str
    ref: str

class PullRequest(BaseModel):
    number: int
    title: str
    body: str | None = None
    state: str
    user: GitHubUser
    head: PullRequestHead
    base: PullRequestBase
    draft: bool = False
    additions: int = 0
    deletions: int = 0
    changed_files: int = 0

class PullRequestEvent(BaseModel):
    action: Literal["opened", "synchronize", "reopened", "closed", "edited"]
    number: int
    pull_request: PullRequest
    repository: GitHubRepository
    installation: GitHubInstallation
    sender: GitHubUser

class IssueComment(BaseModel):
    id: int
    body: str
    user: GitHubUser

class Issue(BaseModel):
    number: int
    title: str
    pull_request: dict | None = None  # Present if issue is a PR

class IssueCommentEvent(BaseModel):
    action: Literal["created", "edited", "deleted"]
    issue: Issue
    comment: IssueComment
    repository: GitHubRepository
    installation: GitHubInstallation
    sender: GitHubUser

class InstallationEvent(BaseModel):
    action: Literal["created", "deleted", "suspend", "unsuspend"]
    installation: GitHubInstallation
    repositories: list[GitHubRepository] = Field(default_factory=list)
    sender: GitHubUser

class InstallationRepositoriesEvent(BaseModel):
    action: Literal["added", "removed"]
    installation: GitHubInstallation
    repositories_added: list[GitHubRepository] = Field(default_factory=list)
    repositories_removed: list[GitHubRepository] = Field(default_factory=list)
    sender: GitHubUser
```

---

## API Endpoints

### Webhook Endpoints

```python
# src/procrasturbate/api/webhooks.py

from fastapi import APIRouter, Request, HTTPException, Header, Depends
from ..services.github_auth import verify_webhook_signature
from ..schemas.github_webhooks import (
    PullRequestEvent,
    IssueCommentEvent,
    InstallationEvent,
    InstallationRepositoriesEvent,
)
from ..tasks.review_tasks import process_pull_request, process_comment_command
from ..services.installation_manager import handle_installation_event, handle_repos_event

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

@router.post("/github")
async def github_webhook(
    request: Request,
    x_github_event: str = Header(..., alias="X-GitHub-Event"),
    x_hub_signature_256: str = Header(..., alias="X-Hub-Signature-256"),
):
    """
    Main GitHub webhook endpoint.
    Handles: pull_request, issue_comment, installation, installation_repositories
    """
    body = await request.body()
    
    # Verify signature
    if not verify_webhook_signature(body, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    payload = await request.json()
    
    match x_github_event:
        case "pull_request":
            event = PullRequestEvent(**payload)
            if event.action in ("opened", "synchronize", "reopened"):
                # Queue review task
                await process_pull_request.defer_async(
                    installation_id=event.installation.id,
                    repo_full_name=event.repository.full_name,
                    pr_number=event.number,
                    action=event.action,
                )
            return {"status": "queued"}
        
        case "issue_comment":
            event = IssueCommentEvent(**payload)
            # Only process comments on PRs that mention @reviewer
            if (
                event.action == "created"
                and event.issue.pull_request is not None
                and "@reviewer" in event.comment.body.lower()
            ):
                await process_comment_command.defer_async(
                    installation_id=event.installation.id,
                    repo_full_name=event.repository.full_name,
                    pr_number=event.issue.number,
                    comment_body=event.comment.body,
                    comment_author=event.comment.user.login,
                )
            return {"status": "queued"}
        
        case "installation":
            event = InstallationEvent(**payload)
            await handle_installation_event(event)
            return {"status": "processed"}
        
        case "installation_repositories":
            event = InstallationRepositoriesEvent(**payload)
            await handle_repos_event(event)
            return {"status": "processed"}
        
        case "ping":
            return {"status": "pong"}
        
        case _:
            return {"status": "ignored", "event": x_github_event}
```

### Admin Endpoints

```python
# src/procrasturbate/api/admin.py

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime
from typing import Literal

from ..database import get_session
from ..models import Installation, Repository, Review, UsageRecord
from ..schemas.admin import (
    InstallationListResponse,
    InstallationDetailResponse,
    RepositoryResponse,
    ReviewListResponse,
    UsageResponse,
    UpdateInstallationRequest,
    UpdateRepositoryRequest,
)

router = APIRouter(prefix="/admin", tags=["admin"])

# Simple API key auth for admin endpoints
async def verify_admin_key(x_admin_key: str = Header(..., alias="X-Admin-Key")):
    if x_admin_key != settings.admin_api_key:
        raise HTTPException(status_code=401, detail="Invalid admin key")


@router.get("/installations", response_model=InstallationListResponse)
async def list_installations(
    session: AsyncSession = Depends(get_session),
    _: None = Depends(verify_admin_key),
):
    """List all GitHub App installations"""
    result = await session.execute(
        select(Installation).order_by(Installation.created_at.desc())
    )
    return {"installations": result.scalars().all()}


@router.get("/installations/{installation_id}", response_model=InstallationDetailResponse)
async def get_installation(
    installation_id: int,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(verify_admin_key),
):
    """Get installation details with repos and usage"""
    installation = await session.get(Installation, installation_id)
    if not installation:
        raise HTTPException(status_code=404, detail="Installation not found")
    
    # Get current month usage
    now = datetime.utcnow()
    usage = await session.execute(
        select(UsageRecord).where(
            UsageRecord.installation_id == installation_id,
            UsageRecord.year == now.year,
            UsageRecord.month == now.month,
        )
    )
    
    return {
        "installation": installation,
        "current_usage": usage.scalar_one_or_none(),
    }


@router.patch("/installations/{installation_id}")
async def update_installation(
    installation_id: int,
    update: UpdateInstallationRequest,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(verify_admin_key),
):
    """Update installation settings (budget, active status)"""
    installation = await session.get(Installation, installation_id)
    if not installation:
        raise HTTPException(status_code=404, detail="Installation not found")
    
    if update.monthly_budget_cents is not None:
        installation.monthly_budget_cents = update.monthly_budget_cents
    if update.is_active is not None:
        installation.is_active = update.is_active
    
    await session.commit()
    return {"status": "updated"}


@router.get("/repositories", response_model=list[RepositoryResponse])
async def list_repositories(
    installation_id: int | None = None,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(verify_admin_key),
):
    """List repositories, optionally filtered by installation"""
    query = select(Repository).order_by(Repository.full_name)
    if installation_id:
        query = query.where(Repository.installation_id == installation_id)
    
    result = await session.execute(query)
    return result.scalars().all()


@router.patch("/repositories/{repository_id}")
async def update_repository(
    repository_id: int,
    update: UpdateRepositoryRequest,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(verify_admin_key),
):
    """Update repository settings"""
    repo = await session.get(Repository, repository_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    
    if update.is_enabled is not None:
        repo.is_enabled = update.is_enabled
    if update.auto_review is not None:
        repo.auto_review = update.auto_review
    if update.monthly_budget_cents is not None:
        repo.monthly_budget_cents = update.monthly_budget_cents
    
    await session.commit()
    return {"status": "updated"}


@router.get("/reviews", response_model=ReviewListResponse)
async def list_reviews(
    repository_id: int | None = None,
    status: str | None = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(verify_admin_key),
):
    """List reviews with filtering"""
    query = select(Review).order_by(Review.created_at.desc()).limit(limit).offset(offset)
    
    if repository_id:
        query = query.where(Review.repository_id == repository_id)
    if status:
        query = query.where(Review.status == status)
    
    result = await session.execute(query)
    return {"reviews": result.scalars().all()}


@router.get("/usage/summary")
async def usage_summary(
    year: int | None = None,
    month: int | None = None,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(verify_admin_key),
):
    """Get usage summary across all installations"""
    now = datetime.utcnow()
    year = year or now.year
    month = month or now.month
    
    result = await session.execute(
        select(
            func.sum(UsageRecord.total_input_tokens).label("total_input_tokens"),
            func.sum(UsageRecord.total_output_tokens).label("total_output_tokens"),
            func.sum(UsageRecord.total_cost_cents).label("total_cost_cents"),
            func.sum(UsageRecord.total_reviews).label("total_reviews"),
        ).where(
            UsageRecord.year == year,
            UsageRecord.month == month,
        )
    )
    row = result.one()
    
    return {
        "year": year,
        "month": month,
        "total_input_tokens": row.total_input_tokens or 0,
        "total_output_tokens": row.total_output_tokens or 0,
        "total_cost_cents": row.total_cost_cents or 0,
        "total_reviews": row.total_reviews or 0,
    }
```

### Health Endpoints

```python
# src/procrasturbate/api/health.py

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from ..database import get_session

router = APIRouter(tags=["health"])

@router.get("/health")
async def health_check():
    return {"status": "ok"}

@router.get("/health/ready")
async def readiness_check(session: AsyncSession = Depends(get_session)):
    """Check database connectivity"""
    try:
        await session.execute(text("SELECT 1"))
        return {"status": "ready", "database": "connected"}
    except Exception as e:
        return {"status": "not ready", "database": str(e)}
```

---

## Core Services

### GitHub Client

```python
# src/procrasturbate/services/github_client.py

import httpx
from typing import Any
from ..utils.github_auth import get_installation_token

class GitHubClient:
    """Async GitHub API client with installation auth"""
    
    BASE_URL = "https://api.github.com"
    
    def __init__(self, installation_id: int):
        self.installation_id = installation_id
        self._token: str | None = None
        self._client: httpx.AsyncClient | None = None
    
    async def __aenter__(self):
        self._token = await get_installation_token(self.installation_id)
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/vnd.github.v3+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=30.0,
        )
        return self
    
    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()
    
    async def get_pull_request(self, owner: str, repo: str, pr_number: int) -> dict[str, Any]:
        """Get PR details"""
        response = await self._client.get(f"/repos/{owner}/{repo}/pulls/{pr_number}")
        response.raise_for_status()
        return response.json()
    
    async def get_pull_request_diff(self, owner: str, repo: str, pr_number: int) -> str:
        """Get PR diff in unified format"""
        response = await self._client.get(
            f"/repos/{owner}/{repo}/pulls/{pr_number}",
            headers={"Accept": "application/vnd.github.v3.diff"},
        )
        response.raise_for_status()
        return response.text
    
    async def get_pull_request_files(self, owner: str, repo: str, pr_number: int) -> list[dict]:
        """Get list of files changed in PR"""
        files = []
        page = 1
        while True:
            response = await self._client.get(
                f"/repos/{owner}/{repo}/pulls/{pr_number}/files",
                params={"per_page": 100, "page": page},
            )
            response.raise_for_status()
            batch = response.json()
            if not batch:
                break
            files.extend(batch)
            page += 1
        return files
    
    async def get_file_content(self, owner: str, repo: str, path: str, ref: str) -> str:
        """Get file content at specific ref"""
        response = await self._client.get(
            f"/repos/{owner}/{repo}/contents/{path}",
            params={"ref": ref},
            headers={"Accept": "application/vnd.github.v3.raw"},
        )
        response.raise_for_status()
        return response.text
    
    async def create_review(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        commit_sha: str,
        body: str,
        event: str = "COMMENT",  # COMMENT, APPROVE, REQUEST_CHANGES
        comments: list[dict] | None = None,
    ) -> dict[str, Any]:
        """
        Create a PR review with optional line comments.
        
        Comments format:
        [
            {
                "path": "src/file.py",
                "position": 5,  # Position in diff, NOT line number
                "body": "Comment text"
            }
        ]
        """
        payload = {
            "commit_id": commit_sha,
            "body": body,
            "event": event,
        }
        if comments:
            payload["comments"] = comments
        
        response = await self._client.post(
            f"/repos/{owner}/{repo}/pulls/{pr_number}/reviews",
            json=payload,
        )
        response.raise_for_status()
        return response.json()
    
    async def add_reaction(self, owner: str, repo: str, comment_id: int, reaction: str) -> None:
        """Add reaction to a comment (eyes, rocket, etc.)"""
        await self._client.post(
            f"/repos/{owner}/{repo}/issues/comments/{comment_id}/reactions",
            json={"content": reaction},
            headers={"Accept": "application/vnd.github.squirrel-girl-preview+json"},
        )
    
    async def create_issue_comment(self, owner: str, repo: str, issue_number: int, body: str) -> dict:
        """Create a comment on an issue/PR"""
        response = await self._client.post(
            f"/repos/{owner}/{repo}/issues/{issue_number}/comments",
            json={"body": body},
        )
        response.raise_for_status()
        return response.json()
```

### Diff Parser

```python
# src/procrasturbate/services/diff_parser.py

import re
from dataclasses import dataclass
from typing import Iterator

@dataclass
class DiffHunk:
    """A single hunk from a unified diff"""
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: list[str]
    header: str

@dataclass
class FileDiff:
    """Parsed diff for a single file"""
    old_path: str
    new_path: str
    hunks: list[DiffHunk]
    is_new: bool = False
    is_deleted: bool = False
    is_renamed: bool = False
    is_binary: bool = False

@dataclass
class LinePosition:
    """Maps a line number in the new file to its position in the diff"""
    file_path: str
    line_number: int  # Line in the actual file
    diff_position: int  # Position in the diff (for GitHub API)
    content: str
    is_addition: bool


def parse_diff(diff_text: str) -> list[FileDiff]:
    """Parse a unified diff into structured FileDiff objects"""
    files = []
    current_file = None
    current_hunk = None
    
    lines = diff_text.split("\n")
    i = 0
    
    while i < len(lines):
        line = lines[i]
        
        # New file header
        if line.startswith("diff --git"):
            if current_file:
                files.append(current_file)
            
            # Parse paths from "diff --git a/path b/path"
            match = re.match(r"diff --git a/(.+) b/(.+)", line)
            if match:
                current_file = FileDiff(
                    old_path=match.group(1),
                    new_path=match.group(2),
                    hunks=[],
                )
            current_hunk = None
            i += 1
            continue
        
        # Check for new/deleted file markers
        if current_file:
            if line.startswith("new file mode"):
                current_file.is_new = True
            elif line.startswith("deleted file mode"):
                current_file.is_deleted = True
            elif line.startswith("rename from"):
                current_file.is_renamed = True
            elif line.startswith("Binary files"):
                current_file.is_binary = True
        
        # Hunk header
        if line.startswith("@@"):
            match = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)", line)
            if match and current_file:
                current_hunk = DiffHunk(
                    old_start=int(match.group(1)),
                    old_count=int(match.group(2)) if match.group(2) else 1,
                    new_start=int(match.group(3)),
                    new_count=int(match.group(4)) if match.group(4) else 1,
                    lines=[],
                    header=match.group(5).strip(),
                )
                current_file.hunks.append(current_hunk)
            i += 1
            continue
        
        # Diff content lines
        if current_hunk is not None and (
            line.startswith("+") or line.startswith("-") or line.startswith(" ") or line == ""
        ):
            current_hunk.lines.append(line)
        
        i += 1
    
    if current_file:
        files.append(current_file)
    
    return files


def get_line_positions(file_diff: FileDiff) -> dict[int, LinePosition]:
    """
    Build a mapping from new file line numbers to diff positions.
    
    GitHub's review API requires the "position" in the diff, not the line number.
    Position is 1-indexed and counts all lines in the diff (including context and removals).
    """
    positions = {}
    
    if file_diff.is_deleted or file_diff.is_binary:
        return positions
    
    diff_position = 0  # Position in the diff (1-indexed when used)
    
    for hunk in file_diff.hunks:
        diff_position += 1  # Count the @@ header line
        new_line = hunk.new_start
        
        for line in hunk.lines:
            diff_position += 1
            
            if line.startswith("+"):
                # Addition - this line exists in new file
                positions[new_line] = LinePosition(
                    file_path=file_diff.new_path,
                    line_number=new_line,
                    diff_position=diff_position,
                    content=line[1:],  # Remove the + prefix
                    is_addition=True,
                )
                new_line += 1
            elif line.startswith("-"):
                # Deletion - skip, no line number in new file
                pass
            else:
                # Context line
                positions[new_line] = LinePosition(
                    file_path=file_diff.new_path,
                    line_number=new_line,
                    diff_position=diff_position,
                    content=line[1:] if line.startswith(" ") else line,
                    is_addition=False,
                )
                new_line += 1
    
    return positions


def build_position_index(files: list[FileDiff]) -> dict[str, dict[int, LinePosition]]:
    """
    Build a complete index: {file_path: {line_number: LinePosition}}
    """
    index = {}
    for file_diff in files:
        if not file_diff.is_binary and not file_diff.is_deleted:
            index[file_diff.new_path] = get_line_positions(file_diff)
    return index


def filter_files_by_patterns(
    files: list[FileDiff],
    include_patterns: list[str],
    exclude_patterns: list[str],
) -> list[FileDiff]:
    """Filter files by glob patterns"""
    import fnmatch
    
    def matches_any(path: str, patterns: list[str]) -> bool:
        return any(fnmatch.fnmatch(path, p) for p in patterns)
    
    filtered = []
    for f in files:
        path = f.new_path
        
        # Check include patterns (if specified)
        if include_patterns and not matches_any(path, include_patterns):
            continue
        
        # Check exclude patterns
        if exclude_patterns and matches_any(path, exclude_patterns):
            continue
        
        filtered.append(f)
    
    return filtered
```

### Claude Client

```python
# src/procrasturbate/services/claude_client.py

import anthropic
from dataclasses import dataclass
from ..config import settings

@dataclass
class ReviewResponse:
    """Structured response from Claude"""
    summary: str
    risk_level: str  # low, medium, high, critical
    comments: list[dict]  # [{file, line, severity, category, message, suggested_fix?}]
    input_tokens: int
    output_tokens: int


REVIEW_SYSTEM_PROMPT = """You are an expert code reviewer. Review the provided pull request diff and provide:

1. A summary of the changes (2-3 sentences)
2. An overall risk level: low, medium, high, or critical
3. Specific comments on issues you find

For each comment, provide:
- file: The file path
- line: The line number in the NEW version of the file (not the old version)
- severity: critical, warning, suggestion, or nitpick
- category: One of: security, bug, performance, style, documentation, maintainability
- message: Clear explanation of the issue
- suggested_fix: (optional) Code suggestion to fix the issue

Focus on:
{focus_areas}

Additional context about this codebase:
{additional_context}

{custom_instructions}

Respond with valid JSON in this exact format:
{
  "summary": "Brief summary of the PR",
  "risk_level": "low|medium|high|critical",
  "comments": [
    {
      "file": "path/to/file.py",
      "line": 42,
      "severity": "warning",
      "category": "security",
      "message": "Explanation of the issue",
      "suggested_fix": "Optional code fix"
    }
  ]
}

If the code looks good with no issues, return an empty comments array.
Only comment on lines that exist in the diff (additions or context lines).
Do not comment on removed lines."""


class ClaudeClient:
    def __init__(self):
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    
    async def review_diff(
        self,
        diff_content: str,
        pr_title: str,
        pr_description: str | None,
        config: "ReviewConfig",
        context_content: str | None = None,
    ) -> ReviewResponse:
        """Generate a review for the given diff"""
        
        # Build focus areas from config
        focus_areas = []
        if config.rules.security:
            focus_areas.append("- Security vulnerabilities, injection risks, auth issues")
        if config.rules.performance:
            focus_areas.append("- Performance problems, inefficient algorithms, N+1 queries")
        if config.rules.style:
            focus_areas.append("- Code style, naming conventions, readability")
        if config.rules.bugs:
            focus_areas.append("- Logic errors, edge cases, null handling")
        if config.rules.documentation:
            focus_areas.append("- Missing or outdated documentation, unclear code")
        
        for name, description in config.rules.custom.items():
            focus_areas.append(f"- {name}: {description}")
        
        # Build context
        additional_context = ""
        if config.languages:
            additional_context += f"Languages: {', '.join(config.languages)}\n"
        if config.frameworks:
            additional_context += f"Frameworks: {', '.join(config.frameworks)}\n"
        if context_content:
            additional_context += f"\nRepository documentation:\n{context_content}\n"
        
        system_prompt = REVIEW_SYSTEM_PROMPT.format(
            focus_areas="\n".join(focus_areas) if focus_areas else "General code quality",
            additional_context=additional_context or "No additional context provided.",
            custom_instructions=config.additional_instructions or "",
        )
        
        user_message = f"""# Pull Request: {pr_title}

{f"## Description{chr(10)}{pr_description}" if pr_description else ""}

## Diff

```diff
{diff_content}
```

Please review this pull request and provide your analysis as JSON."""
        
        model = config.model or settings.default_model
        
        response = await self.client.messages.create(
            model=model,
            max_tokens=settings.max_tokens_per_review,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        
        # Parse response
        import json
        response_text = response.content[0].text
        
        # Handle potential markdown code blocks
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0]
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0]
        
        try:
            data = json.loads(response_text.strip())
        except json.JSONDecodeError:
            # Fallback if JSON parsing fails
            data = {
                "summary": "Failed to parse structured response. Raw output: " + response_text[:500],
                "risk_level": "medium",
                "comments": [],
            }
        
        return ReviewResponse(
            summary=data.get("summary", ""),
            risk_level=data.get("risk_level", "medium"),
            comments=data.get("comments", []),
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
```

### Cost Tracker

```python
# src/procrasturbate/services/cost_tracker.py

from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from ..models import Installation, Repository, UsageRecord
from ..config import settings


def calculate_cost_cents(input_tokens: int, output_tokens: int) -> int:
    """Calculate cost in cents from token counts"""
    input_cost = (input_tokens / 1_000_000) * settings.input_token_cost_per_million
    output_cost = (output_tokens / 1_000_000) * settings.output_token_cost_per_million
    return int(input_cost + output_cost)


async def check_budget(
    session: AsyncSession,
    installation_id: int,
    repository_id: int | None = None,
) -> tuple[bool, int, int]:
    """
    Check if there's budget remaining.
    Returns: (has_budget, remaining_cents, budget_cents)
    """
    installation = await session.get(Installation, installation_id)
    if not installation or not installation.is_active:
        return False, 0, 0
    
    # Determine budget (repo override or installation default)
    budget_cents = installation.monthly_budget_cents
    if repository_id:
        repo = await session.get(Repository, repository_id)
        if repo and repo.monthly_budget_cents is not None:
            budget_cents = repo.monthly_budget_cents
    
    # Get current month usage
    now = datetime.utcnow()
    result = await session.execute(
        select(UsageRecord).where(
            UsageRecord.installation_id == installation.id,
            UsageRecord.year == now.year,
            UsageRecord.month == now.month,
        )
    )
    usage = result.scalar_one_or_none()
    
    current_spend = usage.total_cost_cents if usage else 0
    remaining = budget_cents - current_spend
    
    return remaining > 0, remaining, budget_cents


async def record_usage(
    session: AsyncSession,
    installation_id: int,
    input_tokens: int,
    output_tokens: int,
    cost_cents: int,
) -> None:
    """Record token usage for the current month"""
    now = datetime.utcnow()
    
    # Upsert usage record
    stmt = insert(UsageRecord).values(
        installation_id=installation_id,
        year=now.year,
        month=now.month,
        total_input_tokens=input_tokens,
        total_output_tokens=output_tokens,
        total_cost_cents=cost_cents,
        total_reviews=1,
    ).on_conflict_do_update(
        constraint="uq_installation_year_month",
        set_={
            "total_input_tokens": UsageRecord.total_input_tokens + input_tokens,
            "total_output_tokens": UsageRecord.total_output_tokens + output_tokens,
            "total_cost_cents": UsageRecord.total_cost_cents + cost_cents,
            "total_reviews": UsageRecord.total_reviews + 1,
            "updated_at": now,
        },
    )
    
    await session.execute(stmt)
    await session.commit()
```

### Review Engine

```python
# src/procrasturbate/services/review_engine.py

from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Repository, Review, ReviewComment, ReviewStatus, ReviewTrigger, CommentSeverity
from .github_client import GitHubClient
from .claude_client import ClaudeClient, ReviewResponse
from .diff_parser import parse_diff, build_position_index, filter_files_by_patterns
from .config_loader import load_repo_config
from .cost_tracker import check_budget, record_usage, calculate_cost_cents
from ..config import settings


class ReviewEngine:
    """Orchestrates the PR review process"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.claude = ClaudeClient()
    
    async def review_pull_request(
        self,
        github_installation_id: int,
        repo_full_name: str,
        pr_number: int,
        trigger: ReviewTrigger,
        triggered_by: str | None = None,
    ) -> Review:
        """
        Main entry point for reviewing a PR.
        
        Steps:
        1. Load repo config and check if enabled
        2. Check budget
        3. Fetch PR details and diff
        4. Filter files by config patterns
        5. Call Claude for review
        6. Post review to GitHub
        7. Record usage and save review
        """
        owner, repo_name = repo_full_name.split("/")
        
        # Get or create repository record
        repo = await self._get_or_create_repo(github_installation_id, repo_full_name)
        
        # Check if reviews are enabled
        if not repo.is_enabled:
            return await self._create_skipped_review(
                repo, pr_number, trigger, triggered_by, "Reviews disabled for this repository"
            )
        
        # Check auto_review setting
        config = await load_repo_config(github_installation_id, repo_full_name, self.session)
        if trigger != ReviewTrigger.COMMAND and not config.auto_review:
            return await self._create_skipped_review(
                repo, pr_number, trigger, triggered_by, "Auto-review disabled"
            )
        
        # Check trigger type against config
        trigger_map = {
            ReviewTrigger.PR_OPENED: "opened",
            ReviewTrigger.PR_SYNCHRONIZE: "synchronize",
            ReviewTrigger.PR_REOPENED: "reopened",
        }
        if trigger != ReviewTrigger.COMMAND and trigger_map.get(trigger) not in config.review_on:
            return await self._create_skipped_review(
                repo, pr_number, trigger, triggered_by, f"Trigger {trigger.value} not enabled"
            )
        
        # Check budget
        has_budget, remaining_cents, budget_cents = await check_budget(
            self.session, repo.installation_id, repo.id
        )
        if not has_budget:
            async with GitHubClient(github_installation_id) as gh:
                await gh.create_issue_comment(
                    owner, repo_name, pr_number,
                    f"⚠️ **AI Review skipped**: Monthly budget of ${budget_cents/100:.2f} has been exceeded. "
                    f"Reviews will resume next month or when the budget is increased."
                )
            return await self._create_skipped_review(
                repo, pr_number, trigger, triggered_by, "Budget exceeded"
            )
        
        # Create review record
        review = Review(
            repository_id=repo.id,
            pr_number=pr_number,
            pr_title="",  # Will be filled in
            pr_author="",
            head_sha="",
            base_sha="",
            status=ReviewStatus.IN_PROGRESS,
            trigger=trigger,
            triggered_by=triggered_by,
            config_snapshot=config.model_dump(),
            started_at=datetime.utcnow(),
        )
        self.session.add(review)
        await self.session.flush()
        
        try:
            async with GitHubClient(github_installation_id) as gh:
                # Fetch PR details
                pr = await gh.get_pull_request(owner, repo_name, pr_number)
                review.pr_title = pr["title"]
                review.pr_author = pr["user"]["login"]
                review.head_sha = pr["head"]["sha"]
                review.base_sha = pr["base"]["sha"]
                
                # Check file count
                if pr["changed_files"] > config.max_files:
                    await gh.create_issue_comment(
                        owner, repo_name, pr_number,
                        f"⚠️ **AI Review skipped**: This PR changes {pr['changed_files']} files, "
                        f"which exceeds the limit of {config.max_files}. "
                        f"Use `@reviewer review path/to/specific/dir` to review specific paths."
                    )
                    review.status = ReviewStatus.SKIPPED
                    review.error_message = f"Too many files: {pr['changed_files']}"
                    await self.session.commit()
                    return review
                
                # Fetch diff
                diff_text = await gh.get_pull_request_diff(owner, repo_name, pr_number)
                
                if len(diff_text) > settings.max_diff_size_bytes:
                    await gh.create_issue_comment(
                        owner, repo_name, pr_number,
                        f"⚠️ **AI Review skipped**: Diff size exceeds {settings.max_diff_size_bytes // 1000}KB limit."
                    )
                    review.status = ReviewStatus.SKIPPED
                    review.error_message = "Diff too large"
                    await self.session.commit()
                    return review
                
                # Parse and filter diff
                parsed_files = parse_diff(diff_text)
                filtered_files = filter_files_by_patterns(
                    parsed_files, config.paths.include, config.paths.exclude
                )
                
                if not filtered_files:
                    review.status = ReviewStatus.COMPLETED
                    review.summary = "No files to review after applying path filters."
                    review.risk_level = "low"
                    await self.session.commit()
                    return review
                
                review.files_reviewed = len(filtered_files)
                
                # Load context files
                context_content = await self._load_context_files(
                    gh, owner, repo_name, pr["head"]["sha"], config.context_files
                )
                
                # Build filtered diff for Claude
                # (In a more sophisticated version, you'd reconstruct just the filtered files)
                # For now, send the full diff and rely on Claude to focus on relevant files
                
                # Call Claude
                claude_response = await self.claude.review_diff(
                    diff_content=diff_text,
                    pr_title=pr["title"],
                    pr_description=pr.get("body"),
                    config=config,
                    context_content=context_content,
                )
                
                # Calculate and check cost
                cost_cents = calculate_cost_cents(
                    claude_response.input_tokens, claude_response.output_tokens
                )
                
                review.input_tokens = claude_response.input_tokens
                review.output_tokens = claude_response.output_tokens
                review.cost_cents = cost_cents
                review.summary = claude_response.summary
                review.risk_level = claude_response.risk_level
                
                # Build position index for line comments
                position_index = build_position_index(filtered_files)
                
                # Prepare GitHub review comments
                github_comments = []
                for comment_data in claude_response.comments:
                    file_path = comment_data.get("file")
                    line_num = comment_data.get("line")
                    
                    # Map to diff position
                    if file_path in position_index and line_num in position_index[file_path]:
                        position = position_index[file_path][line_num]
                        
                        # Build comment body with severity emoji
                        severity_emoji = {
                            "critical": "🔴",
                            "warning": "🟡",
                            "suggestion": "🔵",
                            "nitpick": "⚪",
                        }.get(comment_data.get("severity", "suggestion"), "🔵")
                        
                        body = f"{severity_emoji} **{comment_data.get('category', 'general').title()}**: {comment_data['message']}"
                        
                        if comment_data.get("suggested_fix"):
                            body += f"\n\n```suggestion\n{comment_data['suggested_fix']}\n```"
                        
                        github_comments.append({
                            "path": file_path,
                            "position": position.diff_position,
                            "body": body,
                        })
                        
                        # Save comment to database
                        review_comment = ReviewComment(
                            review_id=review.id,
                            file_path=file_path,
                            line_number=line_num,
                            diff_position=position.diff_position,
                            severity=CommentSeverity(comment_data.get("severity", "suggestion")),
                            category=comment_data.get("category", "general"),
                            message=comment_data["message"],
                            suggested_fix=comment_data.get("suggested_fix"),
                        )
                        self.session.add(review_comment)
                
                # Post review to GitHub
                risk_emoji = {
                    "low": "✅",
                    "medium": "⚠️",
                    "high": "🔶",
                    "critical": "🔴",
                }.get(claude_response.risk_level, "ℹ️")
                
                summary_body = f"""## AI Code Review

{risk_emoji} **Risk Level**: {claude_response.risk_level.upper()}

### Summary
{claude_response.summary}

---
<sub>Reviewed {len(filtered_files)} files • {len(github_comments)} comments • Cost: ${cost_cents/100:.3f}</sub>
"""
                
                if settings.enable_line_comments and github_comments:
                    github_review = await gh.create_review(
                        owner, repo_name, pr_number,
                        commit_sha=pr["head"]["sha"],
                        body=summary_body,
                        event="COMMENT",
                        comments=github_comments,
                    )
                else:
                    github_review = await gh.create_review(
                        owner, repo_name, pr_number,
                        commit_sha=pr["head"]["sha"],
                        body=summary_body,
                        event="COMMENT",
                    )
                
                review.github_review_id = github_review["id"]
                review.comments_posted = len(github_comments)
                review.status = ReviewStatus.COMPLETED
                review.completed_at = datetime.utcnow()
                
                # Record usage
                await record_usage(
                    self.session,
                    repo.installation_id,
                    claude_response.input_tokens,
                    claude_response.output_tokens,
                    cost_cents,
                )
                
                await self.session.commit()
                return review
                
        except Exception as e:
            review.status = ReviewStatus.FAILED
            review.error_message = str(e)
            review.completed_at = datetime.utcnow()
            await self.session.commit()
            raise
    
    async def _get_or_create_repo(self, installation_id: int, repo_full_name: str) -> Repository:
        """Get or create a repository record"""
        from sqlalchemy import select
        from ..models import Installation
        
        # Find installation
        result = await self.session.execute(
            select(Installation).where(Installation.github_installation_id == installation_id)
        )
        installation = result.scalar_one_or_none()
        
        if not installation:
            raise ValueError(f"Installation {installation_id} not found")
        
        # Find or create repo
        result = await self.session.execute(
            select(Repository).where(Repository.full_name == repo_full_name)
        )
        repo = result.scalar_one_or_none()
        
        if not repo:
            repo = Repository(
                installation_id=installation.id,
                github_repo_id=0,  # Will be updated on first webhook
                full_name=repo_full_name,
            )
            self.session.add(repo)
            await self.session.flush()
        
        return repo
    
    async def _create_skipped_review(
        self,
        repo: Repository,
        pr_number: int,
        trigger: ReviewTrigger,
        triggered_by: str | None,
        reason: str,
    ) -> Review:
        """Create a skipped review record"""
        review = Review(
            repository_id=repo.id,
            pr_number=pr_number,
            pr_title="",
            pr_author="",
            head_sha="",
            base_sha="",
            status=ReviewStatus.SKIPPED,
            trigger=trigger,
            triggered_by=triggered_by,
            error_message=reason,
        )
        self.session.add(review)
        await self.session.commit()
        return review
    
    async def _load_context_files(
        self,
        gh: GitHubClient,
        owner: str,
        repo: str,
        ref: str,
        context_files: list[str],
    ) -> str | None:
        """Load context files from repo"""
        if not context_files:
            return None
        
        contents = []
        for path in context_files[:5]:  # Limit to 5 context files
            try:
                content = await gh.get_file_content(owner, repo, path, ref)
                contents.append(f"### {path}\n\n{content[:5000]}")  # Truncate large files
            except Exception:
                pass  # Skip files that don't exist
        
        return "\n\n---\n\n".join(contents) if contents else None
```

### Comment Commands Parser

```python
# src/procrasturbate/services/comment_commands.py

import re
from dataclasses import dataclass
from enum import Enum

class CommandType(str, Enum):
    REVIEW = "review"
    EXPLAIN = "explain"
    SECURITY = "security"
    IGNORE = "ignore"
    CONFIG = "config"
    HELP = "help"

@dataclass
class ParsedCommand:
    command_type: CommandType
    args: list[str]
    raw_text: str


def parse_command(comment_body: str) -> ParsedCommand | None:
    """
    Parse @reviewer commands from comment body.
    
    Supported formats:
    - @reviewer review
    - @reviewer review src/auth/
    - @reviewer explain
    - @reviewer security
    - @reviewer ignore
    - @reviewer config
    - @reviewer help
    """
    # Find @reviewer mention
    pattern = r"@reviewer\s+(\w+)(?:\s+(.+))?"
    match = re.search(pattern, comment_body.lower())
    
    if not match:
        return None
    
    command_str = match.group(1)
    args_str = match.group(2)
    
    try:
        command_type = CommandType(command_str)
    except ValueError:
        return ParsedCommand(
            command_type=CommandType.HELP,
            args=[],
            raw_text=comment_body,
        )
    
    args = args_str.split() if args_str else []
    
    return ParsedCommand(
        command_type=command_type,
        args=args,
        raw_text=comment_body,
    )


HELP_MESSAGE = """## 🤖 AI Reviewer Commands

| Command | Description |
|---------|-------------|
| `@reviewer review` | Trigger a full review of the PR |
| `@reviewer review path/to/dir` | Review only files in the specified path |
| `@reviewer explain` | Get a plain-English explanation of changes |
| `@reviewer security` | Security-focused review only |
| `@reviewer ignore` | Skip automatic reviews for this PR |
| `@reviewer config` | Show the active configuration for this repo |
| `@reviewer help` | Show this help message |
"""
```

---

## Procrastinate Task Definitions

```python
# src/procrasturbate/tasks/worker.py

import procrastinate
from ..config import settings
from ..database import async_engine

# Create procrastinate app
app = procrastinate.App(
    connector=procrastinate.PsycopgConnector(
        conninfo=settings.database_url,
    ),
    import_paths=["procrasturbate.tasks.review_tasks"],
)
```

```python
# src/procrasturbate/tasks/review_tasks.py

from ..tasks.worker import app
from ..database import async_session_factory
from ..services.review_engine import ReviewEngine
from ..services.comment_commands import parse_command, CommandType, HELP_MESSAGE
from ..services.github_client import GitHubClient
from ..models import ReviewTrigger


@app.task(name="process_pull_request", retry=3, pass_context=True)
async def process_pull_request(
    context,
    installation_id: int,
    repo_full_name: str,
    pr_number: int,
    action: str,
):
    """Process a PR event and generate a review"""
    trigger_map = {
        "opened": ReviewTrigger.PR_OPENED,
        "synchronize": ReviewTrigger.PR_SYNCHRONIZE,
        "reopened": ReviewTrigger.PR_REOPENED,
    }
    trigger = trigger_map.get(action, ReviewTrigger.PR_OPENED)
    
    async with async_session_factory() as session:
        engine = ReviewEngine(session)
        await engine.review_pull_request(
            github_installation_id=installation_id,
            repo_full_name=repo_full_name,
            pr_number=pr_number,
            trigger=trigger,
        )


@app.task(name="process_comment_command", retry=2, pass_context=True)
async def process_comment_command(
    context,
    installation_id: int,
    repo_full_name: str,
    pr_number: int,
    comment_body: str,
    comment_author: str,
):
    """Process a @reviewer command from a PR comment"""
    owner, repo = repo_full_name.split("/")
    
    parsed = parse_command(comment_body)
    if not parsed:
        return
    
    async with GitHubClient(installation_id) as gh:
        match parsed.command_type:
            case CommandType.HELP:
                await gh.create_issue_comment(owner, repo, pr_number, HELP_MESSAGE)
            
            case CommandType.REVIEW:
                # TODO: Handle path-specific reviews via parsed.args
                async with async_session_factory() as session:
                    engine = ReviewEngine(session)
                    await engine.review_pull_request(
                        github_installation_id=installation_id,
                        repo_full_name=repo_full_name,
                        pr_number=pr_number,
                        trigger=ReviewTrigger.COMMAND,
                        triggered_by=comment_author,
                    )
            
            case CommandType.CONFIG:
                # TODO: Load and display config
                await gh.create_issue_comment(
                    owner, repo, pr_number,
                    "Config display not yet implemented."
                )
            
            case CommandType.IGNORE:
                # TODO: Mark PR as ignored
                await gh.create_issue_comment(
                    owner, repo, pr_number,
                    "✅ Automatic reviews disabled for this PR."
                )
            
            case _:
                await gh.create_issue_comment(
                    owner, repo, pr_number,
                    f"Command `{parsed.command_type.value}` not yet implemented."
                )
```

---

## GitHub App Setup

### Required Permissions

```yaml
# GitHub App permissions
repository_permissions:
  contents: read          # Read repo files (config, context)
  pull_requests: write    # Create reviews, comments
  metadata: read          # Basic repo info

# Subscribe to these events
events:
  - pull_request
  - issue_comment
  - installation
  - installation_repositories
```

### Auth Flow

```python
# src/procrasturbate/utils/github_auth.py

import time
import jwt
import httpx
from ..config import settings

# Cache installation tokens (they last 1 hour)
_token_cache: dict[int, tuple[str, float]] = {}


def generate_app_jwt() -> str:
    """Generate a JWT for GitHub App authentication"""
    now = int(time.time())
    payload = {
        "iat": now - 60,  # Issued at (60 seconds ago for clock skew)
        "exp": now + (10 * 60),  # Expires in 10 minutes
        "iss": settings.github_app_id,
    }
    return jwt.encode(payload, settings.github_app_private_key, algorithm="RS256")


async def get_installation_token(installation_id: int) -> str:
    """Get an installation access token (cached)"""
    # Check cache
    if installation_id in _token_cache:
        token, expires_at = _token_cache[installation_id]
        if time.time() < expires_at - 60:  # 60 second buffer
            return token
    
    # Request new token
    app_jwt = generate_app_jwt()
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"https://api.github.com/app/installations/{installation_id}/access_tokens",
            headers={
                "Authorization": f"Bearer {app_jwt}",
                "Accept": "application/vnd.github.v3+json",
            },
        )
        response.raise_for_status()
        data = response.json()
    
    token = data["token"]
    # Parse expiration (ISO format) - tokens last 1 hour
    expires_at = time.time() + 3500  # ~58 minutes
    
    _token_cache[installation_id] = (token, expires_at)
    return token


def verify_webhook_signature(payload: bytes, signature: str) -> bool:
    """Verify GitHub webhook signature"""
    import hmac
    import hashlib
    
    expected = hmac.new(
        settings.github_webhook_secret.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()
    
    return hmac.compare_digest(f"sha256={expected}", signature)
```

---

## FastAPI Application

```python
# src/procrasturbate/main.py

from contextlib import asynccontextmanager
from fastapi import FastAPI
from .api.router import router
from .database import init_db
from .config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    yield
    # Shutdown
    pass


app = FastAPI(
    title="Procrasturbate 🍆",
    description="The AI PR reviewer that does the work while you procrastinate",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "procrasturbate.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
```

---

## Docker Setup

```dockerfile
# docker/Dockerfile

FROM python:3.12-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e .

# Copy source
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# Default command (override in docker-compose)
CMD ["uvicorn", "procrasturbate.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```yaml
# docker/docker-compose.yml

services:
  db:
    image: postgres:15
    environment:
      POSTGRES_USER: reviewer
      POSTGRES_PASSWORD: reviewer
      POSTGRES_DB: reviewer
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  app:
    build:
      context: ..
      dockerfile: docker/Dockerfile
    environment:
      DATABASE_URL: postgresql+asyncpg://reviewer:reviewer@db:5432/reviewer
      GITHUB_APP_ID: ${GITHUB_APP_ID}
      GITHUB_APP_PRIVATE_KEY: ${GITHUB_APP_PRIVATE_KEY}
      GITHUB_WEBHOOK_SECRET: ${GITHUB_WEBHOOK_SECRET}
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY}
    ports:
      - "8000:8000"
    depends_on:
      - db

  worker:
    build:
      context: ..
      dockerfile: docker/Dockerfile
    command: procrastinate worker --app=procrasturbate.tasks.worker.app
    environment:
      DATABASE_URL: postgresql+asyncpg://reviewer:reviewer@db:5432/reviewer
      GITHUB_APP_ID: ${GITHUB_APP_ID}
      GITHUB_APP_PRIVATE_KEY: ${GITHUB_APP_PRIVATE_KEY}
      GITHUB_WEBHOOK_SECRET: ${GITHUB_WEBHOOK_SECRET}
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY}
    depends_on:
      - db

volumes:
  pgdata:
```

---

## Frontend

### Stack

- **Jinja2** — Server-side templates
- **HTMX** — Dynamic updates without writing JS
- **Alpine.js** — Client-side state (dropdowns, modals, toggles)
- **Tailwind CSS** — Utility-first styling via CLI
- **DaisyUI** — Tailwind component library (buttons, cards, tables, modals)

### Project Structure Addition

```
src/
└── procrasturbate/
    ├── templates/
    │   ├── base.html              # Base layout with nav, flash messages
    │   ├── components/
    │   │   ├── _button.html       # Reusable button macro
    │   │   ├── _card.html         # Card component
    │   │   ├── _table.html        # Data table with sorting
    │   │   ├── _modal.html        # Modal dialog
    │   │   ├── _badge.html        # Status badges
    │   │   ├── _pagination.html   # Pagination controls
    │   │   └── _flash.html        # Flash messages
    │   ├── dashboard/
    │   │   └── index.html         # Main dashboard
    │   ├── installations/
    │   │   ├── list.html          # All installations
    │   │   ├── detail.html        # Single installation + repos
    │   │   └── _row.html          # HTMX partial for table row
    │   ├── repositories/
    │   │   ├── list.html          # All repos
    │   │   ├── detail.html        # Single repo + reviews
    │   │   └── _settings.html     # HTMX partial for settings form
    │   └── reviews/
    │       ├── list.html          # Review history
    │       └── detail.html        # Single review with comments
    └── static/
        ├── input.css              # Tailwind entry point
        ├── dist/
        │   └── output.css         # Generated (gitignored)
        └── js/
            └── app.js             # Minimal JS (if needed beyond Alpine)
```

### Tailwind + DaisyUI Setup

```css
/* src/procrasturbate/static/input.css */

@tailwind base;
@tailwind components;
@tailwind utilities;

/* Custom overrides if needed */
```

```javascript
// tailwind.config.js (project root)

module.exports = {
  content: ["./src/procrasturbate/templates/**/*.html"],
  theme: {
    extend: {},
  },
  plugins: [require("daisyui")],
  daisyui: {
    themes: ["dark", "light"],
    darkTheme: "dark",
  },
};
```

```json
// package.json (minimal, just for tailwind CLI)
{
  "name": "procrasturbate-frontend",
  "scripts": {
    "css:build": "tailwindcss -i src/procrasturbate/static/input.css -o src/procrasturbate/static/dist/output.css --minify",
    "css:watch": "tailwindcss -i src/procrasturbate/static/input.css -o src/procrasturbate/static/dist/output.css --watch"
  },
  "devDependencies": {
    "tailwindcss": "^3.4.0",
    "daisyui": "^4.5.0"
  }
}
```

### Base Template

```html
<!-- src/procrasturbate/templates/base.html -->
<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{% block title %}Procrasturbate{% endblock %}</title>
  
  <!-- Styles -->
  <link href="{{ url_for('static', path='dist/output.css') }}" rel="stylesheet">
  
  <!-- HTMX -->
  <script src="https://unpkg.com/htmx.org@1.9.10"></script>
  
  <!-- Alpine.js -->
  <script defer src="https://unpkg.com/alpinejs@3.x.x/dist/cdn.min.js"></script>
</head>
<body class="min-h-screen bg-base-200" hx-boost="true">
  
  <!-- Navbar -->
  <div class="navbar bg-base-100 shadow-lg">
    <div class="flex-1">
      <a href="{{ url_for('ui_dashboard') }}" class="btn btn-ghost text-xl">🍆 Procrasturbate</a>
    </div>
    <div class="flex-none">
      <ul class="menu menu-horizontal px-1">
        <li><a href="{{ url_for('ui_dashboard') }}">Dashboard</a></li>
        <li><a href="{{ url_for('ui_installations') }}">Installations</a></li>
        <li><a href="{{ url_for('ui_repositories') }}">Repos</a></li>
        <li><a href="{{ url_for('ui_reviews') }}">Reviews</a></li>
      </ul>
    </div>
  </div>
  
  <!-- Flash messages -->
  <div id="flash-container" class="container mx-auto px-4 mt-4">
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% for category, message in messages %}
        <div class="alert alert-{{ category }} mb-2">
          <span>{{ message }}</span>
        </div>
      {% endfor %}
    {% endwith %}
  </div>
  
  <!-- Main content -->
  <main class="container mx-auto px-4 py-8">
    {% block content %}{% endblock %}
  </main>
  
  <!-- HTMX loading indicator -->
  <div class="htmx-indicator fixed top-0 left-0 right-0">
    <progress class="progress progress-primary w-full"></progress>
  </div>
  
</body>
</html>
```

### Component Macros

```html
<!-- src/procrasturbate/templates/components/_badge.html -->
{% macro status_badge(status) %}
  {% set colors = {
    'completed': 'badge-success',
    'in_progress': 'badge-warning',
    'pending': 'badge-info',
    'failed': 'badge-error',
    'skipped': 'badge-ghost'
  } %}
  <span class="badge {{ colors.get(status, 'badge-ghost') }}">
    {{ status | replace('_', ' ') | title }}
  </span>
{% endmacro %}

{% macro risk_badge(risk_level) %}
  {% set colors = {
    'low': 'badge-success',
    'medium': 'badge-warning',
    'high': 'badge-error',
    'critical': 'badge-error badge-outline'
  } %}
  <span class="badge {{ colors.get(risk_level, 'badge-ghost') }}">
    {{ risk_level | upper }}
  </span>
{% endmacro %}

{% macro cost_display(cents) %}
  <span class="font-mono">${{ "%.2f" | format(cents / 100) }}</span>
{% endmacro %}
```

```html
<!-- src/procrasturbate/templates/components/_card.html -->
{% macro stat_card(title, value, description=None, icon=None) %}
<div class="stat bg-base-100 rounded-box shadow">
  {% if icon %}
  <div class="stat-figure text-primary">{{ icon }}</div>
  {% endif %}
  <div class="stat-title">{{ title }}</div>
  <div class="stat-value">{{ value }}</div>
  {% if description %}
  <div class="stat-desc">{{ description }}</div>
  {% endif %}
</div>
{% endmacro %}
```

```html
<!-- src/procrasturbate/templates/components/_modal.html -->
{% macro confirm_modal(id, title, message, action_url, action_text="Confirm", method="POST") %}
<dialog id="{{ id }}" class="modal" x-data="{ open: false }">
  <div class="modal-box">
    <h3 class="font-bold text-lg">{{ title }}</h3>
    <p class="py-4">{{ message }}</p>
    <div class="modal-action">
      <form method="dialog">
        <button class="btn">Cancel</button>
      </form>
      <form hx-{{ method | lower }}="{{ action_url }}" hx-swap="outerHTML">
        <button type="submit" class="btn btn-primary">{{ action_text }}</button>
      </form>
    </div>
  </div>
  <form method="dialog" class="modal-backdrop">
    <button>close</button>
  </form>
</dialog>
{% endmacro %}
```

### Dashboard Page

```html
<!-- src/procrasturbate/templates/dashboard/index.html -->
{% extends "base.html" %}
{% from "components/_badge.html" import cost_display %}
{% from "components/_card.html" import stat_card %}

{% block title %}Dashboard - Procrasturbate{% endblock %}

{% block content %}
<div class="flex justify-between items-center mb-8">
  <h1 class="text-3xl font-bold">Dashboard</h1>
  <div class="text-sm text-base-content/70">
    {{ current_month }} usage
  </div>
</div>

<!-- Stats grid -->
<div class="stats shadow w-full mb-8">
  {{ stat_card("Total Reviews", stats.total_reviews) }}
  {{ stat_card("Total Spend", cost_display(stats.total_cost_cents)) }}
  {{ stat_card("Input Tokens", "{:,}".format(stats.total_input_tokens)) }}
  {{ stat_card("Output Tokens", "{:,}".format(stats.total_output_tokens)) }}
</div>

<!-- Recent reviews -->
<div class="card bg-base-100 shadow-xl">
  <div class="card-body">
    <h2 class="card-title">Recent Reviews</h2>
    
    <div class="overflow-x-auto">
      <table class="table table-zebra">
        <thead>
          <tr>
            <th>Repository</th>
            <th>PR</th>
            <th>Status</th>
            <th>Risk</th>
            <th>Cost</th>
            <th>Time</th>
          </tr>
        </thead>
        <tbody 
          hx-get="{{ url_for('ui_recent_reviews_partial') }}"
          hx-trigger="every 30s"
          hx-swap="innerHTML"
        >
          {% include "reviews/_table_rows.html" %}
        </tbody>
      </table>
    </div>
    
    <div class="card-actions justify-end">
      <a href="{{ url_for('ui_reviews') }}" class="btn btn-ghost btn-sm">View all →</a>
    </div>
  </div>
</div>

<!-- Installations overview -->
<div class="grid grid-cols-1 md:grid-cols-2 gap-6 mt-8">
  {% for installation in installations %}
  <div class="card bg-base-100 shadow-xl">
    <div class="card-body">
      <h2 class="card-title">
        {{ installation.owner_login }}
        {% if not installation.is_active %}
        <span class="badge badge-error">Suspended</span>
        {% endif %}
      </h2>
      
      <div class="flex justify-between text-sm">
        <span>Budget:</span>
        <span>{{ cost_display(installation.current_usage) }} / {{ cost_display(installation.monthly_budget_cents) }}</span>
      </div>
      
      <progress 
        class="progress progress-primary w-full" 
        value="{{ installation.current_usage }}" 
        max="{{ installation.monthly_budget_cents }}"
      ></progress>
      
      <div class="card-actions justify-end mt-4">
        <a href="{{ url_for('ui_installation_detail', installation_id=installation.id) }}" class="btn btn-sm btn-ghost">
          Manage →
        </a>
      </div>
    </div>
  </div>
  {% endfor %}
</div>
{% endblock %}
```

### Installation Settings (HTMX form)

```html
<!-- src/procrasturbate/templates/installations/_settings.html -->
<form 
  hx-patch="{{ url_for('ui_installation_update', installation_id=installation.id) }}"
  hx-swap="outerHTML"
  hx-target="this"
  class="card bg-base-100 shadow-xl"
  x-data="{ editing: false }"
>
  <div class="card-body">
    <div class="flex justify-between items-center">
      <h2 class="card-title">Settings</h2>
      <button type="button" class="btn btn-sm btn-ghost" @click="editing = !editing">
        <span x-show="!editing">Edit</span>
        <span x-show="editing">Cancel</span>
      </button>
    </div>
    
    <div class="form-control">
      <label class="label">
        <span class="label-text">Monthly Budget</span>
      </label>
      <div class="input-group" x-show="editing">
        <span>$</span>
        <input 
          type="number" 
          name="monthly_budget_dollars" 
          value="{{ installation.monthly_budget_cents // 100 }}"
          class="input input-bordered w-full"
          step="1"
          min="0"
        >
      </div>
      <div x-show="!editing" class="py-2">
        ${{ installation.monthly_budget_cents // 100 }}
      </div>
    </div>
    
    <div class="form-control">
      <label class="label cursor-pointer">
        <span class="label-text">Active</span>
        <input 
          type="checkbox" 
          name="is_active"
          class="toggle toggle-primary"
          {% if installation.is_active %}checked{% endif %}
          :disabled="!editing"
        >
      </label>
    </div>
    
    <div class="card-actions justify-end mt-4" x-show="editing">
      <button type="submit" class="btn btn-primary">
        <span class="htmx-indicator loading loading-spinner loading-sm"></span>
        Save Changes
      </button>
    </div>
  </div>
</form>
```

### Reviews List with Filtering

```html
<!-- src/procrasturbate/templates/reviews/list.html -->
{% extends "base.html" %}
{% from "components/_badge.html" import status_badge, risk_badge, cost_display %}
{% from "components/_pagination.html" import pagination %}

{% block title %}Reviews - Procrasturbate{% endblock %}

{% block content %}
<div class="flex justify-between items-center mb-8">
  <h1 class="text-3xl font-bold">Reviews</h1>
</div>

<!-- Filters -->
<div class="card bg-base-100 shadow mb-6" x-data="{ open: false }">
  <div class="card-body py-3">
    <div class="flex items-center justify-between">
      <span class="font-medium">Filters</span>
      <button class="btn btn-sm btn-ghost" @click="open = !open">
        <span x-show="!open">Show</span>
        <span x-show="open">Hide</span>
      </button>
    </div>
    
    <form 
      x-show="open" 
      x-collapse
      hx-get="{{ url_for('ui_reviews') }}"
      hx-push-url="true"
      hx-target="#reviews-table"
      hx-swap="innerHTML"
      class="grid grid-cols-1 md:grid-cols-4 gap-4 mt-4"
    >
      <select name="repository_id" class="select select-bordered w-full">
        <option value="">All repositories</option>
        {% for repo in repositories %}
        <option value="{{ repo.id }}" {% if repo.id == selected_repo %}selected{% endif %}>
          {{ repo.full_name }}
        </option>
        {% endfor %}
      </select>
      
      <select name="status" class="select select-bordered w-full">
        <option value="">All statuses</option>
        <option value="completed" {% if selected_status == 'completed' %}selected{% endif %}>Completed</option>
        <option value="failed" {% if selected_status == 'failed' %}selected{% endif %}>Failed</option>
        <option value="skipped" {% if selected_status == 'skipped' %}selected{% endif %}>Skipped</option>
        <option value="in_progress" {% if selected_status == 'in_progress' %}selected{% endif %}>In Progress</option>
      </select>
      
      <select name="risk_level" class="select select-bordered w-full">
        <option value="">All risk levels</option>
        <option value="low">Low</option>
        <option value="medium">Medium</option>
        <option value="high">High</option>
        <option value="critical">Critical</option>
      </select>
      
      <button type="submit" class="btn btn-primary">
        Apply Filters
      </button>
    </form>
  </div>
</div>

<!-- Reviews table -->
<div class="card bg-base-100 shadow-xl">
  <div class="card-body">
    <div class="overflow-x-auto" id="reviews-table">
      {% include "reviews/_table.html" %}
    </div>
  </div>
</div>
{% endblock %}
```

```html
<!-- src/procrasturbate/templates/reviews/_table.html -->
{% from "components/_badge.html" import status_badge, risk_badge, cost_display %}
{% from "components/_pagination.html" import pagination %}

<table class="table table-zebra">
  <thead>
    <tr>
      <th>Repository</th>
      <th>PR</th>
      <th>Status</th>
      <th>Risk</th>
      <th>Comments</th>
      <th>Cost</th>
      <th>Time</th>
      <th></th>
    </tr>
  </thead>
  <tbody>
    {% for review in reviews %}
    <tr>
      <td>
        <a href="{{ url_for('ui_repository_detail', repository_id=review.repository_id) }}" class="link">
          {{ review.repository.full_name }}
        </a>
      </td>
      <td>
        <a href="https://github.com/{{ review.repository.full_name }}/pull/{{ review.pr_number }}" 
           target="_blank" 
           class="link">
          #{{ review.pr_number }}
        </a>
        <div class="text-xs text-base-content/70 max-w-xs truncate">
          {{ review.pr_title }}
        </div>
      </td>
      <td>{{ status_badge(review.status.value) }}</td>
      <td>
        {% if review.risk_level %}
          {{ risk_badge(review.risk_level) }}
        {% else %}
          <span class="text-base-content/50">—</span>
        {% endif %}
      </td>
      <td>{{ review.comments_posted }}</td>
      <td>{{ cost_display(review.cost_cents) }}</td>
      <td class="text-sm text-base-content/70">
        {{ review.created_at | timeago }}
      </td>
      <td>
        <a href="{{ url_for('ui_review_detail', review_id=review.id) }}" class="btn btn-ghost btn-xs">
          Details
        </a>
      </td>
    </tr>
    {% else %}
    <tr>
      <td colspan="8" class="text-center py-8 text-base-content/50">
        No reviews found
      </td>
    </tr>
    {% endfor %}
  </tbody>
</table>

{% if pagination_info %}
{{ pagination(pagination_info) }}
{% endif %}
```

### UI Routes

```python
# src/procrasturbate/api/ui.py

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime

from ..database import get_session
from ..models import Installation, Repository, Review, UsageRecord

router = APIRouter(tags=["ui"])

templates = Jinja2Templates(directory="src/procrasturbate/templates")

# Add custom filters
def timeago_filter(dt: datetime) -> str:
    """Convert datetime to human-readable 'time ago' string"""
    if not dt:
        return ""
    delta = datetime.utcnow() - dt
    if delta.days > 30:
        return dt.strftime("%b %d, %Y")
    elif delta.days > 0:
        return f"{delta.days}d ago"
    elif delta.seconds > 3600:
        return f"{delta.seconds // 3600}h ago"
    elif delta.seconds > 60:
        return f"{delta.seconds // 60}m ago"
    else:
        return "just now"

templates.env.filters["timeago"] = timeago_filter


@router.get("/", response_class=HTMLResponse)
async def ui_dashboard(request: Request, session: AsyncSession = Depends(get_session)):
    """Main dashboard view"""
    now = datetime.utcnow()
    
    # Get monthly stats
    usage_result = await session.execute(
        select(
            func.sum(UsageRecord.total_input_tokens).label("total_input_tokens"),
            func.sum(UsageRecord.total_output_tokens).label("total_output_tokens"),
            func.sum(UsageRecord.total_cost_cents).label("total_cost_cents"),
            func.sum(UsageRecord.total_reviews).label("total_reviews"),
        ).where(
            UsageRecord.year == now.year,
            UsageRecord.month == now.month,
        )
    )
    usage = usage_result.one()
    
    stats = {
        "total_input_tokens": usage.total_input_tokens or 0,
        "total_output_tokens": usage.total_output_tokens or 0,
        "total_cost_cents": usage.total_cost_cents or 0,
        "total_reviews": usage.total_reviews or 0,
    }
    
    # Get installations with current usage
    installations_result = await session.execute(
        select(Installation).where(Installation.is_active == True)
    )
    installations = installations_result.scalars().all()
    
    # Get recent reviews
    reviews_result = await session.execute(
        select(Review)
        .order_by(Review.created_at.desc())
        .limit(10)
    )
    recent_reviews = reviews_result.scalars().all()
    
    return templates.TemplateResponse("dashboard/index.html", {
        "request": request,
        "stats": stats,
        "installations": installations,
        "reviews": recent_reviews,
        "current_month": now.strftime("%B %Y"),
    })


@router.get("/installations", response_class=HTMLResponse)
async def ui_installations(request: Request, session: AsyncSession = Depends(get_session)):
    """List all installations"""
    result = await session.execute(
        select(Installation).order_by(Installation.created_at.desc())
    )
    installations = result.scalars().all()
    
    return templates.TemplateResponse("installations/list.html", {
        "request": request,
        "installations": installations,
    })


@router.get("/installations/{installation_id}", response_class=HTMLResponse)
async def ui_installation_detail(
    request: Request,
    installation_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Installation detail view"""
    installation = await session.get(Installation, installation_id)
    if not installation:
        raise HTTPException(status_code=404)
    
    # Get repos for this installation
    repos_result = await session.execute(
        select(Repository)
        .where(Repository.installation_id == installation_id)
        .order_by(Repository.full_name)
    )
    repositories = repos_result.scalars().all()
    
    # Get usage history
    usage_result = await session.execute(
        select(UsageRecord)
        .where(UsageRecord.installation_id == installation_id)
        .order_by(UsageRecord.year.desc(), UsageRecord.month.desc())
        .limit(12)
    )
    usage_history = usage_result.scalars().all()
    
    return templates.TemplateResponse("installations/detail.html", {
        "request": request,
        "installation": installation,
        "repositories": repositories,
        "usage_history": usage_history,
    })


@router.patch("/installations/{installation_id}", response_class=HTMLResponse)
async def ui_installation_update(
    request: Request,
    installation_id: int,
    monthly_budget_dollars: int = Form(...),
    is_active: bool = Form(False),
    session: AsyncSession = Depends(get_session),
):
    """Update installation settings (HTMX)"""
    installation = await session.get(Installation, installation_id)
    if not installation:
        raise HTTPException(status_code=404)
    
    installation.monthly_budget_cents = monthly_budget_dollars * 100
    installation.is_active = is_active
    await session.commit()
    
    # Return the updated settings partial
    return templates.TemplateResponse("installations/_settings.html", {
        "request": request,
        "installation": installation,
    })


@router.get("/reviews", response_class=HTMLResponse)
async def ui_reviews(
    request: Request,
    repository_id: int | None = None,
    status: str | None = None,
    risk_level: str | None = None,
    page: int = 1,
    session: AsyncSession = Depends(get_session),
):
    """Reviews list with filtering"""
    query = select(Review).order_by(Review.created_at.desc())
    
    if repository_id:
        query = query.where(Review.repository_id == repository_id)
    if status:
        query = query.where(Review.status == status)
    if risk_level:
        query = query.where(Review.risk_level == risk_level)
    
    # Pagination
    per_page = 25
    query = query.limit(per_page).offset((page - 1) * per_page)
    
    result = await session.execute(query)
    reviews = result.scalars().all()
    
    # Get repos for filter dropdown
    repos_result = await session.execute(select(Repository).order_by(Repository.full_name))
    repositories = repos_result.scalars().all()
    
    context = {
        "request": request,
        "reviews": reviews,
        "repositories": repositories,
        "selected_repo": repository_id,
        "selected_status": status,
        "selected_risk": risk_level,
        "page": page,
    }
    
    # Return partial for HTMX requests
    if request.headers.get("HX-Request"):
        return templates.TemplateResponse("reviews/_table.html", context)
    
    return templates.TemplateResponse("reviews/list.html", context)


@router.get("/reviews/{review_id}", response_class=HTMLResponse)
async def ui_review_detail(
    request: Request,
    review_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Single review detail"""
    review = await session.get(Review, review_id)
    if not review:
        raise HTTPException(status_code=404)
    
    return templates.TemplateResponse("reviews/detail.html", {
        "request": request,
        "review": review,
    })
```

### Build Integration

Update the Dockerfile to build CSS:

```dockerfile
# docker/Dockerfile

FROM node:20-slim AS css-builder
WORKDIR /build
COPY package.json tailwind.config.js ./
COPY src/procrasturbate/static/input.css ./src/procrasturbate/static/
COPY src/procrasturbate/templates ./src/procrasturbate/templates
RUN npm install && npm run css:build

FROM python:3.12-slim
WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e .

# Copy source
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# Copy built CSS from builder
COPY --from=css-builder /build/src/procrasturbate/static/dist ./src/procrasturbate/static/dist

CMD ["uvicorn", "procrasturbate.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Static Files Mount

```python
# In main.py, add static file serving

from fastapi.staticfiles import StaticFiles

app.mount("/static", StaticFiles(directory="src/procrasturbate/static"), name="static")
```

---

## pyproject.toml

```toml
[project]
name = "procrasturbate"
version = "0.1.0"
description = "The AI PR reviewer that does the work while you procrastinate"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.109.0",
    "uvicorn[standard]>=0.27.0",
    "pydantic>=2.5.0",
    "pydantic-settings>=2.1.0",
    "sqlalchemy[asyncio]>=2.0.25",
    "asyncpg>=0.29.0",
    "alembic>=1.13.0",
    "httpx>=0.26.0",
    "anthropic>=0.39.0",
    "procrastinate[asyncio]>=2.0.0",
    "pyjwt[crypto]>=2.8.0",
    "pyyaml>=6.0.1",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=4.1.0",
    "ruff>=0.1.0",
    "mypy>=1.8.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.ruff]
target-version = "py311"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP"]

[tool.mypy]
python_version = "3.11"
strict = true
```

---

## Implementation Order

1. **Phase 1: Foundation**
   - Project scaffolding
   - Database models + Alembic migrations
   - Settings/config
   - GitHub App creation + auth utilities

2. **Phase 2: Core Flow**
   - Webhook endpoint (signature verification)
   - GitHub client (fetch PR, diff, post comments)
   - Diff parser
   - Basic Claude integration
   - Summary-only reviews (no line comments)

3. **Phase 3: Line Comments**
   - Position mapping in diff parser
   - Structured Claude output parsing
   - Review API integration with comments

4. **Phase 4: Configuration**
   - `.aireviewer.yaml` loading
   - Path filtering
   - Context file loading

5. **Phase 5: Cost Control**
   - Usage tracking
   - Budget checks
   - Skip notifications

6. **Phase 6: Commands**
   - Comment parsing
   - Command handlers
   - Help output

7. **Phase 7: Admin API**
   - Admin API endpoints
   - API key auth

8. **Phase 8: Frontend Foundation**
   - Tailwind + DaisyUI setup
   - Base template with nav
   - Static files serving
   - Jinja2 filters (timeago, etc.)

9. **Phase 9: Frontend Pages**
   - Dashboard with stats
   - Installations list + detail
   - Repositories list + detail
   - Reviews list with filtering

10. **Phase 10: Frontend Interactivity**
    - HTMX form submissions
    - Settings edit forms
    - Live updates (polling)
    - Modals for confirmations

---

## Notes for Implementation

- Use `async with` context managers throughout for proper resource cleanup
- All GitHub API calls should handle rate limiting (check `X-RateLimit-Remaining` header)
- Claude responses can be malformed; always wrap JSON parsing in try/except
- Line position calculation is the trickiest part; write thorough tests with real diffs
- GitHub's review API is atomic; if any comment position is invalid, the whole review fails
- Consider adding a "dry run" mode for testing without posting to GitHub

---

## Clarifications & Implementation Decisions

### Database Connections

Two separate connection strings are needed:
- **SQLAlchemy**: Uses `asyncpg` driver → `postgresql+asyncpg://user:pass@host:port/db`
- **Procrastinate**: Uses `psycopg` v3 driver → `postgresql://user:pass@host:port/db`

Both can connect to the same PostgreSQL database; they're just different Python drivers.

```python
# In config.py
database_url: str = Field(..., description="SQLAlchemy connection string (postgresql+asyncpg://...)")
procrastinate_database_url: str = Field(..., description="Procrastinate connection string (postgresql://...)")
```

### Admin Authentication

No authentication for the admin UI initially. The assumption is the service runs behind a VPN or firewall. Authentication can be added later (OAuth, basic auth, etc.).

Remove `X-Admin-Key` header checks from admin endpoints for now.

### Installation Manager Implementation

```python
# src/procrasturbate/services/installation_manager.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..models import Installation, Repository
from ..schemas.github_webhooks import InstallationEvent, InstallationRepositoriesEvent
from ..database import async_session_factory


async def handle_installation_event(event: InstallationEvent) -> None:
    """Handle installation created/deleted/suspend/unsuspend events"""
    async with async_session_factory() as session:
        match event.action:
            case "created":
                installation = Installation(
                    github_installation_id=event.installation.id,
                    owner_type="Organization" if hasattr(event.installation.account, 'type') else "User",
                    owner_login=event.installation.account.login,
                    owner_github_id=event.installation.account.id,
                    is_active=True,
                )
                session.add(installation)

                # Add initial repositories
                for repo in event.repositories:
                    repository = Repository(
                        installation_id=installation.id,
                        github_repo_id=repo.id,
                        full_name=repo.full_name,
                        default_branch=repo.default_branch,
                    )
                    session.add(repository)

                await session.commit()

            case "deleted":
                result = await session.execute(
                    select(Installation).where(
                        Installation.github_installation_id == event.installation.id
                    )
                )
                installation = result.scalar_one_or_none()
                if installation:
                    await session.delete(installation)
                    await session.commit()

            case "suspend":
                result = await session.execute(
                    select(Installation).where(
                        Installation.github_installation_id == event.installation.id
                    )
                )
                installation = result.scalar_one_or_none()
                if installation:
                    installation.is_active = False
                    installation.suspended_at = datetime.utcnow()
                    await session.commit()

            case "unsuspend":
                result = await session.execute(
                    select(Installation).where(
                        Installation.github_installation_id == event.installation.id
                    )
                )
                installation = result.scalar_one_or_none()
                if installation:
                    installation.is_active = True
                    installation.suspended_at = None
                    await session.commit()


async def handle_repos_event(event: InstallationRepositoriesEvent) -> None:
    """Handle repositories added/removed from installation"""
    async with async_session_factory() as session:
        # Find installation
        result = await session.execute(
            select(Installation).where(
                Installation.github_installation_id == event.installation.id
            )
        )
        installation = result.scalar_one_or_none()
        if not installation:
            return

        if event.action == "added":
            for repo in event.repositories_added:
                repository = Repository(
                    installation_id=installation.id,
                    github_repo_id=repo.id,
                    full_name=repo.full_name,
                    default_branch=repo.default_branch,
                )
                session.add(repository)

        elif event.action == "removed":
            for repo in event.repositories_removed:
                result = await session.execute(
                    select(Repository).where(Repository.github_repo_id == repo.id)
                )
                repository = result.scalar_one_or_none()
                if repository:
                    await session.delete(repository)

        await session.commit()
```

### Config Loader Implementation

```python
# src/procrasturbate/services/config_loader.py

import yaml
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..models import Repository
from ..schemas.repo_config import ReviewConfig
from .github_client import GitHubClient


# Cache config for 5 minutes to avoid hitting GitHub API on every request
CONFIG_CACHE_TTL = timedelta(minutes=5)


async def load_repo_config(
    github_installation_id: int,
    repo_full_name: str,
    session: AsyncSession,
) -> ReviewConfig:
    """
    Load .aireviewer.yaml from repository.

    Strategy:
    1. Check if we have a cached config that's still fresh
    2. If not, fetch from GitHub and cache
    3. If file doesn't exist, return defaults
    """
    owner, repo_name = repo_full_name.split("/")

    # Find repository record
    result = await session.execute(
        select(Repository).where(Repository.full_name == repo_full_name)
    )
    repo = result.scalar_one_or_none()

    # Check cache freshness
    if repo and repo.config_yaml and repo.config_fetched_at:
        if datetime.utcnow() - repo.config_fetched_at < CONFIG_CACHE_TTL:
            return ReviewConfig(**repo.config_yaml)

    # Fetch from GitHub
    try:
        async with GitHubClient(github_installation_id) as gh:
            # Try to get config file from default branch
            default_branch = repo.default_branch if repo else "main"
            content = await gh.get_file_content(
                owner, repo_name, ".aireviewer.yaml", default_branch
            )
            config_dict = yaml.safe_load(content)
            config = ReviewConfig(**config_dict) if config_dict else ReviewConfig()
    except Exception:
        # File doesn't exist or couldn't be parsed, use defaults
        config = ReviewConfig()
        config_dict = config.model_dump()

    # Update cache
    if repo:
        repo.config_yaml = config.model_dump()
        repo.config_fetched_at = datetime.utcnow()
        await session.commit()

    return config
```

### Session/Flash Messages

Instead of Starlette's session-based flash messages, use a simpler approach with HTMX:
- Return flash messages as part of HTMX responses using `HX-Trigger` header
- Use Alpine.js to display toast notifications

```python
# Helper for flash messages via HTMX
from fastapi import Response

def flash_message(response: Response, message: str, category: str = "info") -> None:
    """Add flash message via HTMX trigger"""
    import json
    response.headers["HX-Trigger"] = json.dumps({
        "showFlash": {"message": message, "category": category}
    })
```

### GitHub App Setup Documentation

See `docs/github-app-setup.md` for detailed instructions on:
1. Creating a GitHub App
2. Configuring permissions
3. Generating private key
4. Setting up webhook URL
5. Installing the app on repositories
