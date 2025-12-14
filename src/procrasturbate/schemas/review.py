"""Review request/response schemas."""

from pydantic import BaseModel


class ReviewRequest(BaseModel):
    """Request to trigger a review."""

    installation_id: int
    repo_full_name: str
    pr_number: int


class ReviewResponse(BaseModel):
    """Response after triggering a review."""

    review_id: int
    status: str
    message: str
