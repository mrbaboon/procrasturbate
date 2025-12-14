"""Orchestrates the PR review process."""

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models import (
    CommentSeverity,
    Installation,
    Repository,
    Review,
    ReviewComment,
    ReviewStatus,
    ReviewTrigger,
)
from .claude_client import ClaudeClient
from .config_loader import load_repo_config
from .cost_tracker import calculate_cost_cents, check_budget, record_usage
from .diff_parser import build_position_index, filter_files_by_patterns, parse_diff
from .github_client import GitHubClient

logger = logging.getLogger(__name__)


class ReviewEngine:
    """Orchestrates the PR review process."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.claude = ClaudeClient()

    async def review_pull_request(
        self,
        github_installation_id: int,
        repo_full_name: str,
        pr_number: int,
        trigger: ReviewTrigger,
        triggered_by: str | None = None,
        expected_head_sha: str | None = None,
    ) -> Review:
        """
        Main entry point for reviewing a PR.

        Steps:
        1. Load repo config and check if enabled
        2. Check budget
        3. Fetch PR details and diff
        4. Filter files by config patterns
        5. Call Claude for review
        6. Post review to GitHub
        7. Record usage and save review
        """
        owner, repo_name = repo_full_name.split("/")

        # Get or create repository record
        repo = await self._get_or_create_repo(github_installation_id, repo_full_name)

        # Check if reviews are enabled
        if not repo.is_enabled:
            return await self._create_skipped_review(
                repo, pr_number, trigger, triggered_by, "Reviews disabled for this repository"
            )

        # Check auto_review setting
        config = await load_repo_config(github_installation_id, repo_full_name, self.session)
        if trigger != ReviewTrigger.COMMAND and not config.auto_review:
            return await self._create_skipped_review(
                repo, pr_number, trigger, triggered_by, "Auto-review disabled"
            )

        # Check trigger type against config
        trigger_map = {
            ReviewTrigger.PR_OPENED: "opened",
            ReviewTrigger.PR_SYNCHRONIZE: "synchronize",
            ReviewTrigger.PR_REOPENED: "reopened",
        }
        if trigger != ReviewTrigger.COMMAND and trigger_map.get(trigger) not in config.review_on:
            return await self._create_skipped_review(
                repo, pr_number, trigger, triggered_by, f"Trigger {trigger.value} not enabled"
            )

        # Check budget
        has_budget, remaining_cents, budget_cents = await check_budget(
            self.session, repo.installation_id, repo.id
        )
        if not has_budget:
            async with GitHubClient(github_installation_id) as gh:
                await gh.create_issue_comment(
                    owner,
                    repo_name,
                    pr_number,
                    f"**AI Review skipped**: Monthly budget of ${budget_cents / 100:.2f} "
                    f"has been exceeded. Reviews will resume next month or when the budget "
                    f"is increased.",
                )
            return await self._create_skipped_review(
                repo, pr_number, trigger, triggered_by, "Budget exceeded"
            )

        # Create review record
        review = Review(
            repository_id=repo.id,
            pr_number=pr_number,
            pr_title="",  # Will be filled in
            pr_author="",
            head_sha="",
            base_sha="",
            status=ReviewStatus.IN_PROGRESS,
            trigger=trigger,
            triggered_by=triggered_by,
            config_snapshot=config.model_dump(),
            started_at=datetime.utcnow(),
        )
        self.session.add(review)
        await self.session.flush()

        try:
            async with GitHubClient(github_installation_id) as gh:
                # Fetch PR details
                pr = await gh.get_pull_request(owner, repo_name, pr_number)
                review.pr_title = pr["title"]
                review.pr_author = pr["user"]["login"]
                review.head_sha = pr["head"]["sha"]
                review.base_sha = pr["base"]["sha"]

                # Create GitHub check run to show review in progress
                try:
                    check_run = await gh.create_check_run(
                        owner,
                        repo_name,
                        name="AI Code Review",
                        head_sha=pr["head"]["sha"],
                        status="in_progress",
                        output={
                            "title": "Review in progress",
                            "summary": f"Analyzing PR #{pr_number}: {pr['title']}",
                        },
                    )
                    review.github_check_run_id = check_run["id"]
                    await self.session.flush()
                except Exception as e:
                    # Check run creation is optional - don't fail the review
                    logger.warning(f"Failed to create check run: {e}")

                # Check file count
                if pr["changed_files"] > config.max_files:
                    await gh.create_issue_comment(
                        owner,
                        repo_name,
                        pr_number,
                        f"**AI Review skipped**: This PR changes {pr['changed_files']} files, "
                        f"which exceeds the limit of {config.max_files}. "
                        f"Use `@reviewer review path/to/specific/dir` to review specific paths.",
                    )
                    review.status = ReviewStatus.SKIPPED
                    review.error_message = f"Too many files: {pr['changed_files']}"
                    await self.session.commit()
                    return review

                # Fetch diff
                diff_text = await gh.get_pull_request_diff(owner, repo_name, pr_number)

                if len(diff_text) > settings.max_diff_size_bytes:
                    await gh.create_issue_comment(
                        owner,
                        repo_name,
                        pr_number,
                        f"**AI Review skipped**: Diff size exceeds "
                        f"{settings.max_diff_size_bytes // 1000}KB limit.",
                    )
                    review.status = ReviewStatus.SKIPPED
                    review.error_message = "Diff too large"
                    await self.session.commit()
                    return review

                # Parse and filter diff
                parsed_files = parse_diff(diff_text)
                filtered_files = filter_files_by_patterns(
                    parsed_files, config.paths.include, config.paths.exclude
                )

                if not filtered_files:
                    review.status = ReviewStatus.COMPLETED
                    review.summary = "No files to review after applying path filters."
                    review.risk_level = "low"
                    await self.session.commit()
                    return review

                review.files_reviewed = len(filtered_files)

                # Load context files
                context_content = await self._load_context_files(
                    gh, owner, repo_name, pr["head"]["sha"], config.context_files
                )

                # Before the expensive Claude API call, check if a newer commit exists.
                # This saves money when commits come in rapid succession.
                if expected_head_sha and expected_head_sha != pr["head"]["sha"]:
                    logger.info(
                        f"Cancelling review for {repo_full_name}#{pr_number}: "
                        f"expected sha {expected_head_sha[:8]} but PR is now at {pr['head']['sha'][:8]}"
                    )
                    review.status = ReviewStatus.SUPERSEDED
                    review.error_message = (
                        f"Superseded by newer commit {pr['head']['sha'][:8]}"
                    )
                    review.completed_at = datetime.utcnow()
                    await self._update_check_run(
                        gh, owner, repo_name, review.github_check_run_id, review
                    )
                    await self.session.commit()
                    return review

                # Re-fetch PR to double-check head SHA right before calling Claude
                # (handles race condition if commit arrived during diff parsing)
                current_pr = await gh.get_pull_request(owner, repo_name, pr_number)
                if current_pr["head"]["sha"] != pr["head"]["sha"]:
                    logger.info(
                        f"Cancelling review for {repo_full_name}#{pr_number}: "
                        f"new commit detected ({current_pr['head']['sha'][:8]})"
                    )
                    review.status = ReviewStatus.SUPERSEDED
                    review.error_message = (
                        f"Superseded by newer commit {current_pr['head']['sha'][:8]}"
                    )
                    review.completed_at = datetime.utcnow()
                    await self._update_check_run(
                        gh, owner, repo_name, review.github_check_run_id, review
                    )
                    await self.session.commit()
                    return review

                # Call Claude
                claude_response = await self.claude.review_diff(
                    diff_content=diff_text,
                    pr_title=pr["title"],
                    pr_description=pr.get("body"),
                    config=config,
                    context_content=context_content,
                )

                # Calculate cost
                cost_cents = calculate_cost_cents(
                    claude_response.input_tokens, claude_response.output_tokens
                )

                review.input_tokens = claude_response.input_tokens
                review.output_tokens = claude_response.output_tokens
                review.cost_cents = cost_cents
                review.summary = claude_response.summary
                review.risk_level = claude_response.risk_level

                # Build position index for line comments
                position_index = build_position_index(filtered_files)

                # Prepare GitHub review comments
                github_comments: list[dict] = []
                for comment_data in claude_response.comments:
                    file_path = comment_data.get("file")
                    line_num = comment_data.get("line")

                    # Map to diff position
                    if file_path in position_index and line_num in position_index[file_path]:
                        position = position_index[file_path][line_num]

                        # Build comment body with severity emoji
                        severity_emoji = {
                            "critical": "[CRITICAL]",
                            "warning": "[WARNING]",
                            "suggestion": "[SUGGESTION]",
                            "nitpick": "[NITPICK]",
                        }.get(comment_data.get("severity", "suggestion"), "[INFO]")

                        category = comment_data.get("category", "general").title()
                        body = f"{severity_emoji} **{category}**: {comment_data['message']}"

                        if comment_data.get("suggested_fix"):
                            body += f"\n\n```suggestion\n{comment_data['suggested_fix']}\n```"

                        github_comments.append(
                            {
                                "path": file_path,
                                "position": position.diff_position,
                                "body": body,
                            }
                        )

                        # Save comment to database
                        severity_str = comment_data.get("severity", "suggestion")
                        try:
                            severity = CommentSeverity(severity_str)
                        except ValueError:
                            severity = CommentSeverity.SUGGESTION

                        review_comment = ReviewComment(
                            review_id=review.id,
                            file_path=file_path,
                            line_number=line_num,
                            diff_position=position.diff_position,
                            severity=severity,
                            category=comment_data.get("category", "general"),
                            message=comment_data["message"],
                            suggested_fix=comment_data.get("suggested_fix"),
                        )
                        self.session.add(review_comment)

                # Post review to GitHub
                risk_emoji = {
                    "low": "[OK]",
                    "medium": "[MEDIUM]",
                    "high": "[HIGH]",
                    "critical": "[CRITICAL]",
                }.get(claude_response.risk_level, "[INFO]")

                summary_body = f"""## AI Code Review

{risk_emoji} **Risk Level**: {claude_response.risk_level.upper()}

### Summary
{claude_response.summary}

---
<sub>Reviewed {len(filtered_files)} files | {len(github_comments)} comments | Cost: ${cost_cents / 100:.3f}</sub>
"""

                if settings.enable_line_comments and github_comments:
                    github_review = await gh.create_review(
                        owner,
                        repo_name,
                        pr_number,
                        commit_sha=pr["head"]["sha"],
                        body=summary_body,
                        event="COMMENT",
                        comments=github_comments,
                    )
                else:
                    github_review = await gh.create_review(
                        owner,
                        repo_name,
                        pr_number,
                        commit_sha=pr["head"]["sha"],
                        body=summary_body,
                        event="COMMENT",
                    )

                review.github_review_id = github_review["id"]
                review.comments_posted = len(github_comments)
                review.status = ReviewStatus.COMPLETED
                review.completed_at = datetime.utcnow()

                # Record usage
                await record_usage(
                    self.session,
                    repo.installation_id,
                    claude_response.input_tokens,
                    claude_response.output_tokens,
                    cost_cents,
                )

                # Update check run to show success
                await self._update_check_run(
                    gh, owner, repo_name, review.github_check_run_id, review
                )

                await self.session.commit()
                return review

        except Exception as e:
            review.status = ReviewStatus.FAILED
            review.error_message = str(e)
            review.completed_at = datetime.utcnow()

            # Update check run to show failure
            if review.github_check_run_id:
                try:
                    async with GitHubClient(github_installation_id) as gh:
                        await self._update_check_run(
                            gh, owner, repo_name, review.github_check_run_id, review
                        )
                except Exception as check_err:
                    logger.warning(f"Failed to update check run on error: {check_err}")

            await self.session.commit()
            raise

    async def _get_or_create_repo(
        self,
        installation_id: int,
        repo_full_name: str,
    ) -> Repository:
        """Get or create a repository record."""
        # Find installation
        result = await self.session.execute(
            select(Installation).where(Installation.github_installation_id == installation_id)
        )
        installation = result.scalar_one_or_none()

        if not installation:
            raise ValueError(f"Installation {installation_id} not found")

        # Find or create repo
        result = await self.session.execute(
            select(Repository).where(Repository.full_name == repo_full_name)
        )
        repo = result.scalar_one_or_none()

        if not repo:
            repo = Repository(
                installation_id=installation.id,
                github_repo_id=0,  # Will be updated on first webhook
                full_name=repo_full_name,
            )
            self.session.add(repo)
            await self.session.flush()

        return repo

    async def _create_skipped_review(
        self,
        repo: Repository,
        pr_number: int,
        trigger: ReviewTrigger,
        triggered_by: str | None,
        reason: str,
    ) -> Review:
        """Create a skipped review record."""
        review = Review(
            repository_id=repo.id,
            pr_number=pr_number,
            pr_title="",
            pr_author="",
            head_sha="",
            base_sha="",
            status=ReviewStatus.SKIPPED,
            trigger=trigger,
            triggered_by=triggered_by,
            error_message=reason,
        )
        self.session.add(review)
        await self.session.commit()
        return review

    async def _update_check_run(
        self,
        gh: GitHubClient,
        owner: str,
        repo_name: str,
        check_run_id: int | None,
        review: Review,
    ) -> None:
        """Update GitHub check run with final status."""
        if not check_run_id:
            return

        try:
            # Map review status to check run conclusion
            conclusion_map = {
                ReviewStatus.COMPLETED: "success",
                ReviewStatus.FAILED: "failure",
                ReviewStatus.SKIPPED: "skipped",
                ReviewStatus.SUPERSEDED: "cancelled",
            }
            conclusion = conclusion_map.get(review.status, "neutral")

            # Build output based on status
            if review.status == ReviewStatus.COMPLETED:
                title = f"Review complete - {review.risk_level.upper() if review.risk_level else 'OK'}"
                summary = review.summary or "Review completed successfully."
                if review.comments_posted:
                    summary += f"\n\n**{review.comments_posted} comments** posted."
            elif review.status == ReviewStatus.SUPERSEDED:
                title = "Review cancelled"
                summary = review.error_message or "Superseded by newer commit."
            elif review.status == ReviewStatus.SKIPPED:
                title = "Review skipped"
                summary = review.error_message or "Review was skipped."
            else:
                title = "Review failed"
                summary = review.error_message or "An error occurred during review."

            await gh.update_check_run(
                owner,
                repo_name,
                check_run_id,
                status="completed",
                conclusion=conclusion,
                output={"title": title, "summary": summary},
            )
        except Exception as e:
            logger.warning(f"Failed to update check run: {e}")

    async def _load_context_files(
        self,
        gh: GitHubClient,
        owner: str,
        repo: str,
        ref: str,
        context_files: list[str],
    ) -> str | None:
        """Load context files from repo."""
        if not context_files:
            return None

        contents: list[str] = []
        for path in context_files[:5]:  # Limit to 5 context files
            try:
                content = await gh.get_file_content(owner, repo, path, ref)
                contents.append(f"### {path}\n\n{content[:5000]}")  # Truncate large files
            except Exception:
                pass  # Skip files that don't exist

        return "\n\n---\n\n".join(contents) if contents else None
