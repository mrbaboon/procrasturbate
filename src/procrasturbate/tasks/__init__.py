"""Procrastinate task definitions."""

from .review_tasks import process_comment_command, process_pull_request
from .worker import app as procrastinate_app

__all__ = [
    "process_comment_command",
    "process_pull_request",
    "procrastinate_app",
]
