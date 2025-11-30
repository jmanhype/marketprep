"""Authentication API routes.

Endpoints:
- POST /auth/register: Register new vendor account
- POST /auth/login: Authenticate vendor and return tokens
- POST /auth/refresh: Refresh access token using refresh token
"""
from fastapi import APIRouter, Depends, HTTPException, status
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from uuid import uuid4

from src.database import get_db
from src.models.vendor import Vendor
from src.schemas.auth import (
    LoginRequest,
    RefreshTokenRequest,
    TokenResponse,
    RefreshResponse,
    VendorResponse,
)
from src.services.auth_service import AuthService


router = APIRouter(prefix="/auth", tags=["authentication"])

# Password hashing context (bcrypt)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Auth service instance
auth_service = AuthService()


class RegisterRequest(BaseModel):
    """Registration request"""
    email: EmailStr
    password: str
    business_name: str


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(
    registration: RegisterRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Register new vendor account.

    Args:
        registration: Email, password, and business name
        db: Database session (injected)

    Returns:
        TokenResponse with access_token, refresh_token, and vendor info

    Raises:
        HTTPException: 400 if email already exists or password too weak
    """
    # Check if email already exists
    existing_vendor = db.query(Vendor).filter(Vendor.email == registration.email).first()
    if existing_vendor:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Validate password strength (basic validation)
    if len(registration.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters",
        )

    # Hash password
    password_hash = pwd_context.hash(registration.password)

    # Create new vendor
    new_vendor = Vendor(
        id=uuid4(),
        email=registration.email,
        password_hash=password_hash,
        business_name=registration.business_name,
        subscription_tier="mvp",  # Start with MVP tier (per subscription model constraints)
        subscription_status="trial",  # New accounts start in trial
    )

    db.add(new_vendor)
    db.commit()
    db.refresh(new_vendor)

    # Generate tokens
    access_token = auth_service.generate_access_token(
        vendor_id=new_vendor.id,
        email=new_vendor.email,
    )

    refresh_token = auth_service.generate_refresh_token(vendor_id=new_vendor.id)

    # Prepare vendor response
    vendor_response = VendorResponse(
        id=new_vendor.id,
        email=new_vendor.email,
        business_name=new_vendor.business_name,
        subscription_tier=new_vendor.subscription_tier,
        subscription_status=new_vendor.subscription_status,
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        vendor=vendor_response,
    )


@router.post("/login", response_model=TokenResponse, status_code=status.HTTP_200_OK)
def login(
    credentials: LoginRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Authenticate vendor and return access and refresh tokens.

    Args:
        credentials: Email and password
        db: Database session (injected)

    Returns:
        TokenResponse with access_token, refresh_token, and vendor info

    Raises:
        HTTPException: 401 if credentials are invalid
    """
    # Find vendor by email
    vendor = db.query(Vendor).filter(Vendor.email == credentials.email).first()

    if not vendor:
        # Don't reveal whether email exists (security best practice)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # Verify password
    if not pwd_context.verify(credentials.password, vendor.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # Generate tokens
    access_token = auth_service.generate_access_token(
        vendor_id=vendor.id,
        email=vendor.email,
    )

    refresh_token = auth_service.generate_refresh_token(vendor_id=vendor.id)

    # Prepare vendor response
    vendor_response = VendorResponse(
        id=vendor.id,
        email=vendor.email,
        business_name=vendor.business_name,
        subscription_tier=vendor.subscription_tier,
        subscription_status=vendor.subscription_status,
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        vendor=vendor_response,
    )


@router.post("/refresh", response_model=RefreshResponse, status_code=status.HTTP_200_OK)
def refresh_access_token(
    request: RefreshTokenRequest,
) -> RefreshResponse:
    """Generate new access token from valid refresh token.

    Args:
        request: Refresh token and email

    Returns:
        RefreshResponse with new access_token

    Raises:
        HTTPException: 401 if refresh token is invalid or expired
    """
    from src.services.auth_service import (
        TokenExpiredError,
        InvalidTokenError,
        InvalidTokenTypeError,
    )

    try:
        # Generate new access token from refresh token
        new_access_token = auth_service.refresh_access_token(
            refresh_token=request.refresh_token,
            email=request.email,
        )

        return RefreshResponse(
            access_token=new_access_token,
            token_type="bearer",
        )

    except TokenExpiredError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Refresh token expired: {str(e)}",
        ) from e

    except (InvalidTokenError, InvalidTokenTypeError) as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid refresh token: {str(e)}",
        ) from e
