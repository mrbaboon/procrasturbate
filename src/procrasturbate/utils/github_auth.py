"""GitHub App authentication utilities."""

import hashlib
import hmac
import time

import httpx
import jwt

from ..config import settings

# Cache installation tokens (they last 1 hour)
_token_cache: dict[int, tuple[str, float]] = {}


def generate_app_jwt() -> str:
    """Generate a JWT for GitHub App authentication."""
    now = int(time.time())
    payload = {
        "iat": now - 60,  # Issued at (60 seconds ago for clock skew)
        "exp": now + (10 * 60),  # Expires in 10 minutes
        "iss": settings.github_app_id,
    }
    return jwt.encode(payload, settings.github_app_private_key, algorithm="RS256")


async def get_installation_token(installation_id: int) -> str:
    """Get an installation access token (cached)."""
    # Check cache
    if installation_id in _token_cache:
        token, expires_at = _token_cache[installation_id]
        if time.time() < expires_at - 60:  # 60 second buffer
            return token

    # Request new token
    app_jwt = generate_app_jwt()

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"https://api.github.com/app/installations/{installation_id}/access_tokens",
            headers={
                "Authorization": f"Bearer {app_jwt}",
                "Accept": "application/vnd.github.v3+json",
            },
        )
        response.raise_for_status()
        data = response.json()

    token = data["token"]
    # Parse expiration (ISO format) - tokens last 1 hour
    expires_at = time.time() + 3500  # ~58 minutes

    _token_cache[installation_id] = (token, expires_at)
    return token


def verify_webhook_signature(payload: bytes, signature: str) -> bool:
    """Verify GitHub webhook signature."""
    expected = hmac.new(
        settings.github_webhook_secret.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(f"sha256={expected}", signature)
