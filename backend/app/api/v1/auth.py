"""Authentication API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import settings
from app.models.user import User
from app.models.session import Session as SessionModel
from app.services.auth_service import AuthService
from app.middleware.auth import get_current_active_user
from app.schemas.user import (
    UserCreate,
    UserLogin,
    UserResponse,
    TokenResponse,
    RefreshTokenRequest,
    ChangePasswordRequest,
    MessageResponse,
    UserUpdate,
    SessionResponse,
    SessionListResponse,
    DeleteAccountRequest,
)

router = APIRouter()


@router.post("/auth/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(
    user_data: UserCreate,
    db: Session = Depends(get_db)
):
    """Register a new user.

    Args:
        user_data: User registration data
        db: Database session

    Returns:
        Created user

    Raises:
        HTTPException: If email or username already exists
    """
    auth_service = AuthService(db)

    # Check if email already exists
    if auth_service.get_user_by_email(user_data.email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered"
        )

    # Check if username already exists
    if auth_service.get_user_by_username(user_data.username):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already taken"
        )

    user = auth_service.create_user(
        email=user_data.email,
        username=user_data.username,
        password=user_data.password
    )

    return user


@router.post("/auth/login", response_model=TokenResponse)
def login(
    credentials: UserLogin,
    request: Request,
    db: Session = Depends(get_db)
):
    """Authenticate user and return tokens.

    Args:
        credentials: Login credentials (email and password)
        request: FastAPI request object (for device info)
        db: Database session

    Returns:
        Access and refresh tokens

    Raises:
        HTTPException: If credentials are invalid
    """
    auth_service = AuthService(db)

    user = auth_service.authenticate_user(credentials.email, credentials.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )

    # Update last login
    auth_service.update_last_login(user)

    # Generate tokens
    access_token = auth_service.create_access_token(user.id)
    refresh_token = auth_service.create_refresh_token(user.id)

    # Create session for tracking
    device_info = request.headers.get("User-Agent", "Unknown")
    ip_address = request.client.host if request.client else None
    auth_service.create_session(
        user_id=user.id,
        refresh_token=refresh_token,
        device_info=device_info,
        ip_address=ip_address
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


@router.post("/auth/refresh", response_model=TokenResponse)
def refresh_token(
    request: RefreshTokenRequest,
    db: Session = Depends(get_db)
):
    """Refresh access token using refresh token.

    Args:
        request: Refresh token request
        db: Database session

    Returns:
        New access and refresh tokens

    Raises:
        HTTPException: If refresh token is invalid
    """
    payload = AuthService.decode_token(request.refresh_token)

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token"
        )

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type"
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload"
        )

    auth_service = AuthService(db)
    user = auth_service.get_user_by_id(user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )

    # Generate new tokens
    access_token = auth_service.create_access_token(user.id)
    refresh_token = auth_service.create_refresh_token(user.id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


@router.get("/auth/me", response_model=UserResponse)
def get_current_user_info(
    current_user: User = Depends(get_current_active_user)
):
    """Get current authenticated user information.

    Args:
        current_user: Current authenticated user

    Returns:
        User information
    """
    return current_user


@router.post("/auth/change-password", response_model=MessageResponse)
def change_password(
    request: ChangePasswordRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Change current user's password.

    Args:
        request: Password change request
        current_user: Current authenticated user
        db: Database session

    Returns:
        Success message

    Raises:
        HTTPException: If current password is incorrect
    """
    auth_service = AuthService(db)

    # Verify current password
    if not auth_service.verify_password(request.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect"
        )

    # Change password
    auth_service.change_password(current_user, request.new_password)

    return MessageResponse(message="Password changed successfully")


@router.patch("/auth/profile", response_model=UserResponse)
def update_profile(
    data: UserUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Update current user's profile.

    Args:
        data: Profile update data
        current_user: Current authenticated user
        db: Database session

    Returns:
        Updated user information

    Raises:
        HTTPException: If email or username is already taken
    """
    auth_service = AuthService(db)

    try:
        updated_user = auth_service.update_profile(
            user=current_user,
            email=data.email,
            username=data.username
        )
        return updated_user
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )


@router.get("/auth/sessions", response_model=SessionListResponse)
def get_sessions(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get all active sessions for the current user.

    Args:
        current_user: Current authenticated user
        db: Database session

    Returns:
        List of active sessions
    """
    auth_service = AuthService(db)
    sessions = auth_service.get_user_sessions(current_user.id)

    session_responses = [
        SessionResponse(
            id=s.id,
            device_info=s.device_info,
            ip_address=s.ip_address,
            created_at=s.created_at,
            last_activity=s.last_activity,
            is_current=False  # Will be marked by frontend using current token
        )
        for s in sessions
    ]

    return SessionListResponse(sessions=session_responses, total=len(session_responses))


@router.delete("/auth/sessions/{session_id}", response_model=MessageResponse)
def revoke_session(
    session_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Revoke a specific session.

    Args:
        session_id: Session ID to revoke
        current_user: Current authenticated user
        db: Database session

    Returns:
        Success message

    Raises:
        HTTPException: If session not found
    """
    auth_service = AuthService(db)

    if not auth_service.revoke_session(session_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )

    return MessageResponse(message="Session revoked successfully")


@router.post("/auth/logout", response_model=MessageResponse)
def logout(
    request: RefreshTokenRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Logout current session by revoking the refresh token.

    Args:
        request: Request containing the refresh token to revoke
        current_user: Current authenticated user
        db: Database session

    Returns:
        Success message
    """
    auth_service = AuthService(db)

    session = auth_service.get_session_by_token(request.refresh_token)
    if session and session.user_id == current_user.id:
        session.is_active = False
        db.commit()

    return MessageResponse(message="Logged out successfully")


@router.post("/auth/logout-all", response_model=MessageResponse)
def logout_all(
    request: RefreshTokenRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Logout all sessions except the current one.

    Args:
        request: Request containing the current refresh token (to keep)
        current_user: Current authenticated user
        db: Database session

    Returns:
        Success message with count of revoked sessions
    """
    auth_service = AuthService(db)

    # Find current session to exclude it
    current_session = auth_service.get_session_by_token(request.refresh_token)
    except_session_id = current_session.id if current_session else None

    count = auth_service.revoke_all_sessions(current_user.id, except_session_id)

    return MessageResponse(message=f"Logged out from {count} other session(s)")


@router.delete("/auth/account", response_model=MessageResponse)
def delete_account(
    request: DeleteAccountRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Permanently delete the current user's account and all associated data.

    Args:
        request: Request containing password confirmation
        current_user: Current authenticated user
        db: Database session

    Returns:
        Success message

    Raises:
        HTTPException: If password is incorrect
    """
    auth_service = AuthService(db)

    # Verify password
    if not auth_service.verify_password(request.password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect password"
        )

    # Delete user's sessions first (explicit delete to avoid cascade issues)
    db.query(SessionModel).filter(SessionModel.user_id == current_user.id).delete()

    # Delete user
    db.delete(current_user)
    db.commit()

    return MessageResponse(message="Account deleted successfully")
