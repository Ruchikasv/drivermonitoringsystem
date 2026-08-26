"""
FastAPI dependencies for Owner Authentication, JWT tokens, and Cookie authorization.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import jwt
from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings
from app.database.connection import get_connection
from app.database.owner_repository import OwnerRecord, OwnerRepository

bearer_scheme = HTTPBearer(auto_error=False)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Generate a signed JWT access token."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta if expires_delta is not None else timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc)})
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Decode and validate a JWT access token."""
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid, expired, or corrupted authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def get_current_owner(
    request: Request,
    auth_header: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    conn: Any = Depends(get_connection),
) -> OwnerRecord:
    """
    Dependency that enforces owner/fleet manager authentication.
    Supports both Authorization Bearer header and secure HttpOnly cookie.
    """
    token: Optional[str] = None

    if auth_header and auth_header.credentials:
        token = auth_header.credentials
    elif settings.COOKIE_NAME in request.cookies:
        token = request.cookies.get(settings.COOKIE_NAME)

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please log in to access fleet management.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(token)
    sub = payload.get("sub")
    if sub is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload.",
        )

    try:
        owner_id = int(sub)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token subject.",
        )

    repo = OwnerRepository(conn)
    owner = repo.get_owner_by_id(owner_id)

    if owner is None or owner.is_active != 1:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Owner account is deactivated or no longer exists.",
        )

    return owner


def get_optional_owner(
    request: Request,
    auth_header: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    conn: Any = Depends(get_connection),
) -> Optional[OwnerRecord]:
    """Optional owner dependency for endpoints that adapt based on auth state."""
    try:
        return get_current_owner(request, auth_header, conn)
    except HTTPException:
        return None
