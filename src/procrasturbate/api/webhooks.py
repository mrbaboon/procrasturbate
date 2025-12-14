"""GitHub webhook endpoints."""

from fastapi import APIRouter, Header, HTTPException, Request

from ..schemas.github_webhooks import (
    InstallationEvent,
    InstallationRepositoriesEvent,
    IssueCommentEvent,
    PullRequestEvent,
)
from ..services.installation_manager import handle_installation_event, handle_repos_event
from ..tasks.review_tasks import process_comment_command, process_pull_request
from ..utils.github_auth import verify_webhook_signature

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/github")
async def github_webhook(
    request: Request,
    x_github_event: str = Header(..., alias="X-GitHub-Event"),
    x_hub_signature_256: str = Header(..., alias="X-Hub-Signature-256"),
) -> dict:
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
