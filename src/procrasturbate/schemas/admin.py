"""Admin API schemas."""

from datetime import datetime

from pydantic import BaseModel


class InstallationSummary(BaseModel):
    """Summary of an installation."""

    id: int
    github_installation_id: int
    owner_login: str
    owner_type: str
    is_active: bool
    monthly_budget_cents: int
    created_at: datetime

    class Config:
        from_attributes = True


class InstallationListResponse(BaseModel):
    """Response for listing installations."""

    installations: list[InstallationSummary]


class UsageResponse(BaseModel):
    """Usage record summary."""

    id: int
    year: int
    month: int
    total_input_tokens: int
    total_output_tokens: int
    total_cost_cents: int
    total_reviews: int

    class Config:
        from_attributes = True


class InstallationDetailResponse(BaseModel):
    """Detailed installation response."""

    installation: InstallationSummary
    current_usage: UsageResponse | None


class RepositoryResponse(BaseModel):
    """Repository summary."""

    id: int
    installation_id: int
    full_name: str
    is_enabled: bool
    auto_review: bool
    monthly_budget_cents: int | None
    created_at: datetime

    class Config:
        from_attributes = True


class ReviewSummary(BaseModel):
    """Review summary."""

    id: int
    repository_id: int
    pr_number: int
    pr_title: str
    status: str
    risk_level: str | None
    cost_cents: int
    created_at: datetime

    class Config:
        from_attributes = True


class ReviewListResponse(BaseModel):
    """Response for listing reviews."""

    reviews: list[ReviewSummary]


class UpdateInstallationRequest(BaseModel):
    """Request to update installation settings."""

    monthly_budget_cents: int | None = None
    is_active: bool | None = None


class UpdateRepositoryRequest(BaseModel):
    """Request to update repository settings."""

    is_enabled: bool | None = None
    auto_review: bool | None = None
    monthly_budget_cents: int | None = None
