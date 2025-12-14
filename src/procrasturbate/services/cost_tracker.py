"""Token usage and cost tracking."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models import Installation, Repository, UsageRecord


def calculate_cost_cents(input_tokens: int, output_tokens: int) -> int:
    """Calculate cost in cents from token counts."""
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
    """Record token usage for the current month."""
    now = datetime.utcnow()

    # Upsert usage record
    stmt = (
        insert(UsageRecord)
        .values(
            installation_id=installation_id,
            year=now.year,
            month=now.month,
            total_input_tokens=input_tokens,
            total_output_tokens=output_tokens,
            total_cost_cents=cost_cents,
            total_reviews=1,
        )
        .on_conflict_do_update(
            constraint="uq_installation_year_month",
            set_={
                "total_input_tokens": UsageRecord.total_input_tokens + input_tokens,
                "total_output_tokens": UsageRecord.total_output_tokens + output_tokens,
                "total_cost_cents": UsageRecord.total_cost_cents + cost_cents,
                "total_reviews": UsageRecord.total_reviews + 1,
                "updated_at": now,
            },
        )
    )

    await session.execute(stmt)
    await session.commit()
