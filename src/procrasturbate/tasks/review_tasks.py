"""Review task definitions for Procrastinate."""

from ..database import async_session_factory
from ..models import ReviewTrigger
from ..services.comment_commands import HELP_MESSAGE, CommandType, parse_command
from ..services.github_client import GitHubClient
from ..services.review_engine import ReviewEngine
from .worker import app


@app.task(name="process_pull_request", retry=3)
async def process_pull_request(
    installation_id: int,
    repo_full_name: str,
    pr_number: int,
    action: str,
) -> None:
    """Process a PR event and generate a review."""
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


@app.task(name="process_comment_command", retry=2)
async def process_comment_command(
    installation_id: int,
    repo_full_name: str,
    pr_number: int,
    comment_body: str,
    comment_author: str,
) -> None:
    """Process a @reviewer command from a PR comment."""
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
                    owner,
                    repo,
                    pr_number,
                    "Config display not yet implemented.",
                )

            case CommandType.IGNORE:
                # TODO: Mark PR as ignored
                await gh.create_issue_comment(
                    owner,
                    repo,
                    pr_number,
                    "Automatic reviews disabled for this PR.",
                )

            case _:
                await gh.create_issue_comment(
                    owner,
                    repo,
                    pr_number,
                    f"Command `{parsed.command_type.value}` not yet implemented.",
                )
