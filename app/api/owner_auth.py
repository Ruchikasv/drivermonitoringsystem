"""
API Router for Owner / Fleet Manager Registration, Login, and Session Authentication.
"""

import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, EmailStr, field_validator

from app.api.dependencies import create_access_token, get_current_owner
from app.config import settings
from app.database.connection import get_connection
from app.database.owner_repository import OwnerRecord, OwnerRepository

router = APIRouter(prefix="/owner/auth", tags=["Owner Authentication"])


EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")


# ---------------------------------------------------------------------------
# Request & Response Schemas
# ---------------------------------------------------------------------------

class OwnerRegisterRequest(BaseModel):
    name: str
    email: str
    password: str

    @field_validator("name")
    def validate_name(cls, v: str) -> str:
        clean = v.strip()
        if len(clean) < 2:
            raise ValueError("Full name must be at least 2 characters.")
        return clean

    @field_validator("email")
    def validate_email(cls, v: str) -> str:
        clean = v.strip().lower()
        if not EMAIL_REGEX.match(clean):
            raise ValueError("Invalid email format.")
        return clean

    @field_validator("password")
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long.")
        return v


class OwnerLoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    def validate_email(cls, v: str) -> str:
        clean = v.strip().lower()
        if not EMAIL_REGEX.match(clean):
            raise ValueError("Invalid email format.")
        return clean



class OwnerAuthResponse(BaseModel):
    owner_id: int
    name: str
    email: str
    token: str
    message: str


class OwnerProfileResponse(BaseModel):
    owner_id: int
    name: str
    email: str
    created_at: str
    is_active: int


class OwnerCountResponse(BaseModel):
    count: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/count", response_model=OwnerCountResponse)
def get_registered_owners_count(conn=Depends(get_connection)):
    """Return the total number of registered fleet operators (public metric)."""
    repo = OwnerRepository(conn)
    return OwnerCountResponse(count=repo.get_owner_count())


@router.post("/register", response_model=OwnerAuthResponse, status_code=status.HTTP_201_CREATED)
def register_owner(body: OwnerRegisterRequest, response: Response, conn=Depends(get_connection)):
    """Register a new fleet owner account."""
    repo = OwnerRepository(conn)

    if repo.is_email_registered(body.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"An account with email '{body.email}' already exists. Please log in.",
        )

    try:
        owner_id = repo.create_owner(
            name=body.name,
            email=body.email,
            plain_password=body.password,
        )
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))

    # Generate JWT access token
    token = create_access_token({"sub": str(owner_id), "email": body.email, "name": body.name})

    # Set secure HttpOnly cookie
    response.set_cookie(
        key=settings.COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )

    return OwnerAuthResponse(
        owner_id=owner_id,
        name=body.name,
        email=body.email,
        token=token,
        message=f"Fleet owner account '{body.name}' registered successfully.",
    )


@router.post("/login", response_model=OwnerAuthResponse)
def login_owner(body: OwnerLoginRequest, response: Response, conn=Depends(get_connection)):
    """Authenticate a fleet owner via email and password."""
    repo = OwnerRepository(conn)
    owner = repo.authenticate_owner(body.email, body.password)

    if owner is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password. Please check your credentials.",
        )

    token = create_access_token({"sub": str(owner.owner_id), "email": owner.email, "name": owner.name})

    response.set_cookie(
        key=settings.COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )

    return OwnerAuthResponse(
        owner_id=owner.owner_id,
        name=owner.name,
        email=owner.email,
        token=token,
        message=f"Welcome back, {owner.name}!",
    )


@router.get("/me", response_model=OwnerProfileResponse)
def get_current_owner_profile(current_owner: OwnerRecord = Depends(get_current_owner)):
    """Return the profile data for the authenticated fleet manager."""
    return OwnerProfileResponse(
        owner_id=current_owner.owner_id,
        name=current_owner.name,
        email=current_owner.email,
        created_at=current_owner.created_at,
        is_active=current_owner.is_active,
    )


@router.post("/logout")
def logout_owner(response: Response):
    """Clear the owner's authentication cookie session."""
    response.delete_cookie(key=settings.COOKIE_NAME)
    return {"status": "success", "message": "Logged out successfully."}
