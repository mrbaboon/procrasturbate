"""Admin API endpoints."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..models import Installation, Repository, Review, UsageRecord
from ..schemas.admin import (
    InstallationDetailResponse,
    InstallationListResponse,
    InstallationSummary,
    RepositoryResponse,
    ReviewListResponse,
    ReviewSummary,
    UpdateInstallationRequest,
    UpdateRepositoryRequest,
    UsageResponse,
)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/installations", response_model=InstallationListResponse)
async def list_installations(
    session: AsyncSession = Depends(get_session),
) -> InstallationListResponse:
    """List all GitHub App installations."""
    result = await session.execute(
        select(Installation).order_by(Installation.created_at.desc())
    )
    installations = result.scalars().all()
    return InstallationListResponse(
        installations=[InstallationSummary.model_validate(i) for i in installations]
    )


@router.get("/installations/{installation_id}", response_model=InstallationDetailResponse)
async def get_installation(
    installation_id: int,
    session: AsyncSession = Depends(get_session),
) -> InstallationDetailResponse:
    """Get installation details with repos and usage."""
    installation = await session.get(Installation, installation_id)
    if not installation:
        raise HTTPException(status_code=404, detail="Installation not found")

    # Get current month usage
    now = datetime.utcnow()
    usage_result = await session.execute(
        select(UsageRecord).where(
            UsageRecord.installation_id == installation_id,
            UsageRecord.year == now.year,
            UsageRecord.month == now.month,
        )
    )
    usage = usage_result.scalar_one_or_none()

    return InstallationDetailResponse(
        installation=InstallationSummary.model_validate(installation),
        current_usage=UsageResponse.model_validate(usage) if usage else None,
    )


@router.patch("/installations/{installation_id}")
async def update_installation(
    installation_id: int,
    update: UpdateInstallationRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Update installation settings (budget, active status)."""
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
) -> list[RepositoryResponse]:
    """List repositories, optionally filtered by installation."""
    query = select(Repository).order_by(Repository.full_name)
    if installation_id:
        query = query.where(Repository.installation_id == installation_id)

    result = await session.execute(query)
    repos = result.scalars().all()
    return [RepositoryResponse.model_validate(r) for r in repos]


@router.patch("/repositories/{repository_id}")
async def update_repository(
    repository_id: int,
    update: UpdateRepositoryRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Update repository settings."""
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
) -> ReviewListResponse:
    """List reviews with filtering."""
    query = select(Review).order_by(Review.created_at.desc()).limit(limit).offset(offset)

    if repository_id:
        query = query.where(Review.repository_id == repository_id)
    if status:
        query = query.where(Review.status == status)

    result = await session.execute(query)
    reviews = result.scalars().all()
    return ReviewListResponse(reviews=[ReviewSummary.model_validate(r) for r in reviews])


@router.get("/usage/summary")
async def usage_summary(
    year: int | None = None,
    month: int | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Get usage summary across all installations."""
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
