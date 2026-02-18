"""
Authentication and authorization
"""
from fastapi import HTTPException, Header
from app.core.settings import settings


VALID_TOKENS = settings.get_auth_tokens()


async def get_current_user(authorization: str = Header(None)):
    """
    Verify bearer token and return user information

    Args:
        authorization: Authorization header with bearer token

    Returns:
        dict: User information

    Raises:
        HTTPException: If token is missing or invalid
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header missing")

    token = authorization.replace("Bearer ", "")

    if token not in VALID_TOKENS:
        raise HTTPException(status_code=401, detail="Invalid token")

    return VALID_TOKENS[token]
