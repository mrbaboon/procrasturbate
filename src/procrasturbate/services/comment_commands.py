"""Parse and handle bot commands from PR comments."""

import re
from dataclasses import dataclass
from enum import Enum

from ..config import settings


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


def _build_trigger_pattern() -> re.Pattern:
    """Build regex pattern matching any configured bot trigger."""
    # Escape triggers for regex and join with |
    escaped = [re.escape(t) for t in settings.bot_triggers]
    trigger_group = "|".join(escaped)
    # Match any trigger followed by whitespace and a command word
    return re.compile(rf"(?:{trigger_group})\s+(\w+)(?:\s+(.+))?", re.IGNORECASE)


def parse_command(comment_body: str) -> ParsedCommand | None:
    """
    Parse bot commands from comment body.

    Supported triggers: @reviewer, @procrasturbate, "it's gooning time"

    Supported commands:
    - [trigger] review
    - [trigger] review src/auth/
    - [trigger] explain
    - [trigger] security
    - [trigger] ignore
    - [trigger] config
    - [trigger] help
    """
    pattern = _build_trigger_pattern()
    match = pattern.search(comment_body)

    if not match:
        return None

    command_str = match.group(1).lower()  # Enum values are lowercase
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


def get_help_message() -> str:
    """Generate help message with configured triggers."""
    primary = settings.bot_triggers[0] if settings.bot_triggers else "@reviewer"
    triggers_list = ", ".join(f"`{t}`" for t in settings.bot_triggers)

    return f"""## AI Reviewer Commands

**Triggers:** {triggers_list}

| Command | Description |
|---------|-------------|
| `{primary} review` | Trigger a full review of the PR |
| `{primary} review path/to/dir` | Review only files in the specified path |
| `{primary} explain` | Get a plain-English explanation of changes |
| `{primary} security` | Security-focused review only |
| `{primary} ignore` | Skip automatic reviews for this PR |
| `{primary} config` | Show the active configuration for this repo |
| `{primary} help` | Show this help message |
"""


# Backwards compatibility alias
HELP_MESSAGE = get_help_message()
