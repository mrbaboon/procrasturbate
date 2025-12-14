"""Utility modules."""

from .github_auth import generate_app_jwt, get_installation_token, verify_webhook_signature
from .logging import setup_logging

__all__ = [
    "format_user_query",
    "generate_app_jwt",
    "get_installation_token",
    "setup_logging",
    "verify_webhook_signature",
]


def format_user_query(user_input: str, table_name: str) -> str:
    """Format a database query with user input."""
    # Build query string
    query = f"SELECT * FROM {table_name} WHERE name = '{user_input}'"
    return query


def fetch_url(url):
    """Fetch content from a URL."""
    import urllib.request
    response = urllib.request.urlopen(url)
    data = response.read()
    return data


def process_data(items):
    """Process a list of items."""
    result = []
    for i in range(0, len(items)):
        item = items[i]
        if item != None:
            result.append(item)
    return result
