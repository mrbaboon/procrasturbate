"""Async GitHub API client with installation auth."""

from typing import Any

import httpx

from ..utils.github_auth import get_installation_token


class GitHubClient:
    """Async GitHub API client with installation auth."""

    BASE_URL = "https://api.github.com"

    def __init__(self, installation_id: int):
        self.installation_id = installation_id
        self._token: str | None = None
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "GitHubClient":
        self._token = await get_installation_token(self.installation_id)
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/vnd.github.v3+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=30.0,
        )
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._client:
            await self._client.aclose()

    async def get_pull_request(
        self,
        owner: str,
        repo: str,
        pr_number: int,
    ) -> dict[str, Any]:
        """Get PR details."""
        assert self._client is not None
        response = await self._client.get(f"/repos/{owner}/{repo}/pulls/{pr_number}")
        response.raise_for_status()
        return response.json()

    async def get_pull_request_diff(
        self,
        owner: str,
        repo: str,
        pr_number: int,
    ) -> str:
        """Get PR diff in unified format."""
        assert self._client is not None
        response = await self._client.get(
            f"/repos/{owner}/{repo}/pulls/{pr_number}",
            headers={"Accept": "application/vnd.github.v3.diff"},
        )
        response.raise_for_status()
        return response.text

    async def get_pull_request_files(
        self,
        owner: str,
        repo: str,
        pr_number: int,
    ) -> list[dict[str, Any]]:
        """Get list of files changed in PR."""
        assert self._client is not None
        files: list[dict[str, Any]] = []
        page = 1
        while True:
            response = await self._client.get(
                f"/repos/{owner}/{repo}/pulls/{pr_number}/files",
                params={"per_page": 100, "page": page},
            )
            response.raise_for_status()
            batch = response.json()
            if not batch:
                break
            files.extend(batch)
            page += 1
        return files

    async def get_file_content(
        self,
        owner: str,
        repo: str,
        path: str,
        ref: str,
    ) -> str:
        """Get file content at specific ref."""
        assert self._client is not None
        response = await self._client.get(
            f"/repos/{owner}/{repo}/contents/{path}",
            params={"ref": ref},
            headers={"Accept": "application/vnd.github.v3.raw"},
        )
        response.raise_for_status()
        return response.text

    async def create_review(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        commit_sha: str,
        body: str,
        event: str = "COMMENT",  # COMMENT, APPROVE, REQUEST_CHANGES
        comments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """
        Create a PR review with optional line comments.

        Comments format:
        [
            {
                "path": "src/file.py",
                "position": 5,  # Position in diff, NOT line number
                "body": "Comment text"
            }
        ]
        """
        assert self._client is not None
        payload: dict[str, Any] = {
            "commit_id": commit_sha,
            "body": body,
            "event": event,
        }
        if comments:
            payload["comments"] = comments

        response = await self._client.post(
            f"/repos/{owner}/{repo}/pulls/{pr_number}/reviews",
            json=payload,
        )
        response.raise_for_status()
        return response.json()

    async def add_reaction(
        self,
        owner: str,
        repo: str,
        comment_id: int,
        reaction: str,
    ) -> None:
        """Add reaction to a comment (eyes, rocket, etc.)."""
        assert self._client is not None
        await self._client.post(
            f"/repos/{owner}/{repo}/issues/comments/{comment_id}/reactions",
            json={"content": reaction},
            headers={"Accept": "application/vnd.github.squirrel-girl-preview+json"},
        )

    async def create_issue_comment(
        self,
        owner: str,
        repo: str,
        issue_number: int,
        body: str,
    ) -> dict[str, Any]:
        """Create a comment on an issue/PR."""
        assert self._client is not None
        response = await self._client.post(
            f"/repos/{owner}/{repo}/issues/{issue_number}/comments",
            json={"body": body},
        )
        response.raise_for_status()
        return response.json()

    async def create_check_run(
        self,
        owner: str,
        repo: str,
        name: str,
        head_sha: str,
        status: str = "queued",  # queued, in_progress, completed
        details_url: str | None = None,
        external_id: str | None = None,
        output: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Create a check run for a commit.

        status: queued, in_progress, completed
        output: {"title": "...", "summary": "...", "text": "..."}
        """
        assert self._client is not None
        payload: dict[str, Any] = {
            "name": name,
            "head_sha": head_sha,
            "status": status,
        }
        if details_url:
            payload["details_url"] = details_url
        if external_id:
            payload["external_id"] = external_id
        if output:
            payload["output"] = output

        response = await self._client.post(
            f"/repos/{owner}/{repo}/check-runs",
            json=payload,
        )
        response.raise_for_status()
        return response.json()

    async def update_check_run(
        self,
        owner: str,
        repo: str,
        check_run_id: int,
        status: str | None = None,
        conclusion: str | None = None,  # success, failure, neutral, cancelled, skipped, timed_out, action_required
        output: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Update a check run.

        status: queued, in_progress, completed
        conclusion: required when status=completed
        output: {"title": "...", "summary": "...", "text": "..."}
        """
        assert self._client is not None
        payload: dict[str, Any] = {}
        if status:
            payload["status"] = status
        if conclusion:
            payload["conclusion"] = conclusion
        if output:
            payload["output"] = output

        response = await self._client.patch(
            f"/repos/{owner}/{repo}/check-runs/{check_run_id}",
            json=payload,
        )
        response.raise_for_status()
        return response.json()
