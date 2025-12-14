"""UI routes for the admin dashboard."""

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..database import get_session
from ..models import Installation, Repository, Review, UsageRecord

router = APIRouter(tags=["ui"])

# Templates directory
templates_dir = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))


# Custom Jinja2 filters
def timeago_filter(dt: datetime | None) -> str:
    """Convert datetime to human-readable 'time ago' string."""
    if not dt:
        return ""
    # Handle timezone-aware datetimes
    if dt.tzinfo is not None:
        dt = dt.replace(tzinfo=None)
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


def format_cost(cents: int) -> str:
    """Format cents as dollars."""
    return f"${cents / 100:.2f}"


# Register filters
templates.env.filters["timeago"] = timeago_filter
templates.env.filters["format_cost"] = format_cost


@router.get("/", response_class=HTMLResponse)
async def ui_dashboard(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    """Main dashboard view."""
    now = datetime.utcnow()

    # Get monthly stats
    usage_result = await session.execute(
        select(
            func.coalesce(func.sum(UsageRecord.total_input_tokens), 0).label(
                "total_input_tokens"
            ),
            func.coalesce(func.sum(UsageRecord.total_output_tokens), 0).label(
                "total_output_tokens"
            ),
            func.coalesce(func.sum(UsageRecord.total_cost_cents), 0).label(
                "total_cost_cents"
            ),
            func.coalesce(func.sum(UsageRecord.total_reviews), 0).label("total_reviews"),
        ).where(
            UsageRecord.year == now.year,
            UsageRecord.month == now.month,
        )
    )
    usage = usage_result.one()

    stats = {
        "total_input_tokens": usage.total_input_tokens,
        "total_output_tokens": usage.total_output_tokens,
        "total_cost_cents": usage.total_cost_cents,
        "total_reviews": usage.total_reviews,
    }

    # Get installations with current usage
    installations_result = await session.execute(
        select(Installation).where(Installation.is_active == True)
    )
    installations = installations_result.scalars().all()

    # Get recent reviews with repository info
    reviews_result = await session.execute(
        select(Review)
        .options(selectinload(Review.repository))
        .order_by(Review.created_at.desc())
        .limit(10)
    )
    recent_reviews = reviews_result.scalars().all()

    return templates.TemplateResponse(
        "dashboard/index.html",
        {
            "request": request,
            "stats": stats,
            "installations": installations,
            "reviews": recent_reviews,
            "current_month": now.strftime("%B %Y"),
        },
    )


@router.get("/installations", response_class=HTMLResponse)
async def ui_installations(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    """List all installations."""
    result = await session.execute(
        select(Installation).order_by(Installation.created_at.desc())
    )
    installations = result.scalars().all()

    return templates.TemplateResponse(
        "installations/list.html",
        {
            "request": request,
            "installations": installations,
        },
    )


@router.get("/installations/{installation_id}", response_class=HTMLResponse)
async def ui_installation_detail(
    request: Request,
    installation_id: int,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    """Installation detail view."""
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

    # Get current month usage
    now = datetime.utcnow()
    current_usage = next(
        (u for u in usage_history if u.year == now.year and u.month == now.month),
        None,
    )

    return templates.TemplateResponse(
        "installations/detail.html",
        {
            "request": request,
            "installation": installation,
            "repositories": repositories,
            "usage_history": usage_history,
            "current_usage": current_usage,
        },
    )


@router.patch("/installations/{installation_id}", response_class=HTMLResponse)
async def ui_installation_update(
    request: Request,
    installation_id: int,
    monthly_budget_dollars: int = Form(...),
    is_active: bool = Form(False),
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    """Update installation settings (HTMX)."""
    installation = await session.get(Installation, installation_id)
    if not installation:
        raise HTTPException(status_code=404)

    installation.monthly_budget_cents = monthly_budget_dollars * 100
    installation.is_active = is_active
    await session.commit()

    # Return the updated settings partial
    return templates.TemplateResponse(
        "installations/_settings.html",
        {
            "request": request,
            "installation": installation,
        },
    )


@router.get("/repositories", response_class=HTMLResponse)
async def ui_repositories(
    request: Request,
    installation_id: int | None = None,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    """List all repositories."""
    query = select(Repository).options(selectinload(Repository.installation))
    if installation_id:
        query = query.where(Repository.installation_id == installation_id)
    query = query.order_by(Repository.full_name)

    result = await session.execute(query)
    repositories = result.scalars().all()

    # Get installations for filter dropdown
    installations_result = await session.execute(
        select(Installation).order_by(Installation.owner_login)
    )
    installations = installations_result.scalars().all()

    return templates.TemplateResponse(
        "repositories/list.html",
        {
            "request": request,
            "repositories": repositories,
            "installations": installations,
            "selected_installation": installation_id,
        },
    )


@router.get("/repositories/{repository_id}", response_class=HTMLResponse)
async def ui_repository_detail(
    request: Request,
    repository_id: int,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    """Repository detail view."""
    repo = await session.get(Repository, repository_id)
    if not repo:
        raise HTTPException(status_code=404)

    # Get recent reviews
    reviews_result = await session.execute(
        select(Review)
        .where(Review.repository_id == repository_id)
        .order_by(Review.created_at.desc())
        .limit(20)
    )
    reviews = reviews_result.scalars().all()

    return templates.TemplateResponse(
        "repositories/detail.html",
        {
            "request": request,
            "repository": repo,
            "reviews": reviews,
        },
    )


@router.patch("/repositories/{repository_id}", response_class=HTMLResponse)
async def ui_repository_update(
    request: Request,
    repository_id: int,
    is_enabled: bool = Form(False),
    auto_review: bool = Form(False),
    monthly_budget_dollars: int | None = Form(None),
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    """Update repository settings (HTMX)."""
    repo = await session.get(Repository, repository_id)
    if not repo:
        raise HTTPException(status_code=404)

    repo.is_enabled = is_enabled
    repo.auto_review = auto_review
    if monthly_budget_dollars is not None:
        repo.monthly_budget_cents = monthly_budget_dollars * 100
    else:
        repo.monthly_budget_cents = None
    await session.commit()

    return templates.TemplateResponse(
        "repositories/_settings.html",
        {
            "request": request,
            "repository": repo,
        },
    )


@router.get("/reviews", response_class=HTMLResponse)
async def ui_reviews(
    request: Request,
    repository_id: int | None = None,
    status: str | None = None,
    risk_level: str | None = None,
    page: int = 1,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    """Reviews list with filtering."""
    query = (
        select(Review)
        .options(selectinload(Review.repository))
        .order_by(Review.created_at.desc())
    )

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
) -> HTMLResponse:
    """Single review detail."""
    result = await session.execute(
        select(Review)
        .options(selectinload(Review.repository), selectinload(Review.comments))
        .where(Review.id == review_id)
    )
    review = result.scalar_one_or_none()
    if not review:
        raise HTTPException(status_code=404)

    return templates.TemplateResponse(
        "reviews/detail.html",
        {
            "request": request,
            "review": review,
        },
    )
