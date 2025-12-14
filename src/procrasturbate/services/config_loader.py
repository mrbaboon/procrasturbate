"""Load and cache repository configuration."""

from datetime import datetime, timedelta

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
        cache_age = datetime.utcnow() - repo.config_fetched_at.replace(tzinfo=None)
        if cache_age < CONFIG_CACHE_TTL:
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

    # Update cache
    if repo:
        repo.config_yaml = config.model_dump()
        repo.config_fetched_at = datetime.utcnow()
        await session.commit()

    return config
