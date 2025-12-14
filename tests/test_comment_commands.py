"""Tests for comment command parsing."""

import pytest
from procrasturbate.services.comment_commands import parse_command, CommandType


def test_parse_review_command():
    """Test parsing @reviewer review command."""
    result = parse_command("@reviewer review")

    assert result is not None
    assert result.command_type == CommandType.REVIEW
    assert result.args == []


def test_parse_review_with_path():
    """Test parsing @reviewer review with path argument."""
    result = parse_command("@reviewer review src/auth/")

    assert result is not None
    assert result.command_type == CommandType.REVIEW
    assert result.args == ["src/auth/"]


def test_parse_help_command():
    """Test parsing @reviewer help command."""
    result = parse_command("@reviewer help")

    assert result is not None
    assert result.command_type == CommandType.HELP


def test_parse_security_command():
    """Test parsing @reviewer security command."""
    result = parse_command("@reviewer security")

    assert result is not None
    assert result.command_type == CommandType.SECURITY


def test_parse_unknown_command():
    """Test unknown command falls back to help."""
    result = parse_command("@reviewer unknown_command")

    assert result is not None
    assert result.command_type == CommandType.HELP


def test_no_reviewer_mention():
    """Test comment without @reviewer returns None."""
    result = parse_command("This is just a regular comment")

    assert result is None


def test_case_insensitive():
    """Test command parsing is case insensitive."""
    result = parse_command("@REVIEWER REVIEW")

    assert result is not None
    assert result.command_type == CommandType.REVIEW


def test_reviewer_in_middle():
    """Test @reviewer can appear in middle of comment."""
    result = parse_command("Hey, can you @reviewer review this when you get a chance?")

    assert result is not None
    assert result.command_type == CommandType.REVIEW


def test_procrasturbate_trigger():
    """Test @procrasturbate alternate trigger."""
    result = parse_command("@procrasturbate review")

    assert result is not None
    assert result.command_type == CommandType.REVIEW


def test_gooning_time_trigger():
    """Test 'it's gooning time' easter egg trigger."""
    result = parse_command("it's gooning time review")

    assert result is not None
    assert result.command_type == CommandType.REVIEW


def test_gooning_time_case_insensitive():
    """Test easter egg is case insensitive."""
    result = parse_command("IT'S GOONING TIME security")

    assert result is not None
    assert result.command_type == CommandType.SECURITY
