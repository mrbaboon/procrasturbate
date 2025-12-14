"""Handle GitHub App installation events."""

from datetime import datetime

from sqlalchemy import select

from ..database import async_session_factory
from ..models import Installation, Repository
from ..schemas.github_webhooks import InstallationEvent, InstallationRepositoriesEvent


async def handle_installation_event(event: InstallationEvent) -> None:
    """Handle installation created/deleted/suspend/unsuspend events."""
    async with async_session_factory() as session:
        match event.action:
            case "created":
                installation = Installation(
                    github_installation_id=event.installation.id,
                    owner_type=event.installation.account.type,
                    owner_login=event.installation.account.login,
                    owner_github_id=event.installation.account.id,
                    is_active=True,
                )
                session.add(installation)
                await session.flush()  # Get the installation.id

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
    """Handle repositories added/removed from installation."""
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
