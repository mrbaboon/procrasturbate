"""Pydantic models for GitHub webhook payloads."""

from typing import Literal

from pydantic import BaseModel, Field


class GitHubUser(BaseModel):
    """GitHub user or organization."""

    login: str
    id: int
    type: str = "User"  # "User" or "Organization"


class GitHubRepository(BaseModel):
    """GitHub repository info."""

    id: int
    full_name: str
    name: str
    default_branch: str = "main"
    private: bool = False


class GitHubInstallation(BaseModel):
    """GitHub App installation info."""

    id: int
    account: GitHubUser


class PullRequestHead(BaseModel):
    """PR head (source) branch info."""

    sha: str
    ref: str


class PullRequestBase(BaseModel):
    """PR base (target) branch info."""

    sha: str
    ref: str


class PullRequest(BaseModel):
    """Pull request details."""

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
    """Webhook payload for pull_request events."""

    action: Literal["opened", "synchronize", "reopened", "closed", "edited"]
    number: int
    pull_request: PullRequest
    repository: GitHubRepository
    installation: GitHubInstallation
    sender: GitHubUser


class IssueComment(BaseModel):
    """Issue/PR comment."""

    id: int
    body: str
    user: GitHubUser


class Issue(BaseModel):
    """Issue (or PR as issue)."""

    number: int
    title: str
    pull_request: dict | None = None  # Present if issue is a PR


class IssueCommentEvent(BaseModel):
    """Webhook payload for issue_comment events."""

    action: Literal["created", "edited", "deleted"]
    issue: Issue
    comment: IssueComment
    repository: GitHubRepository
    installation: GitHubInstallation
    sender: GitHubUser


class InstallationEvent(BaseModel):
    """Webhook payload for installation events."""

    action: Literal["created", "deleted", "suspend", "unsuspend"]
    installation: GitHubInstallation
    repositories: list[GitHubRepository] = Field(default_factory=list)
    sender: GitHubUser


class InstallationRepositoriesEvent(BaseModel):
    """Webhook payload for installation_repositories events."""

    action: Literal["added", "removed"]
    installation: GitHubInstallation
    repositories_added: list[GitHubRepository] = Field(default_factory=list)
    repositories_removed: list[GitHubRepository] = Field(default_factory=list)
    sender: GitHubUser
