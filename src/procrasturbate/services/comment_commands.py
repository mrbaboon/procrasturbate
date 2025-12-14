"""Parse and handle @reviewer commands from PR comments."""

import re
from dataclasses import dataclass
from enum import Enum


class CommandType(str, Enum):
    """Types of @reviewer commands."""

    REVIEW = "review"
    EXPLAIN = "explain"
    SECURITY = "security"
    IGNORE = "ignore"
    CONFIG = "config"
    HELP = "help"


@dataclass
class ParsedCommand:
    """A parsed @reviewer command."""

    command_type: CommandType
    args: list[str]
    raw_text: str


def parse_command(comment_body: str) -> ParsedCommand | None:
    """
    Parse @reviewer commands from comment body.

    Supported formats:
    - @reviewer review
    - @reviewer review src/auth/
    - @reviewer explain
    - @reviewer security
    - @reviewer ignore
    - @reviewer config
    - @reviewer help
    """
    # Find @reviewer mention
    pattern = r"@reviewer\s+(\w+)(?:\s+(.+))?"
    match = re.search(pattern, comment_body.lower())

    if not match:
        return None

    command_str = match.group(1)
    args_str = match.group(2)

    try:
        command_type = CommandType(command_str)
    except ValueError:
        return ParsedCommand(
            command_type=CommandType.HELP,
            args=[],
            raw_text=comment_body,
        )

    args = args_str.split() if args_str else []

    return ParsedCommand(
        command_type=command_type,
        args=args,
        raw_text=comment_body,
    )


HELP_MESSAGE = """## AI Reviewer Commands

| Command | Description |
|---------|-------------|
| `@reviewer review` | Trigger a full review of the PR |
| `@reviewer review path/to/dir` | Review only files in the specified path |
| `@reviewer explain` | Get a plain-English explanation of changes |
| `@reviewer security` | Security-focused review only |
| `@reviewer ignore` | Skip automatic reviews for this PR |
| `@reviewer config` | Show the active configuration for this repo |
| `@reviewer help` | Show this help message |
"""
