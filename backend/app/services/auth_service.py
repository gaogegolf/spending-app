"""Authentication service for JWT tokens and password management."""

import hashlib
from datetime import datetime, timedelta
from typing import Optional, List

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session as DBSession

from app.config import settings
from app.models.user import User
from app.models.session import Session


# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthService:
    """Service for authentication operations."""

    def __init__(self, db: DBSession):
        """Initialize auth service.

        Args:
            db: Database session
        """
        self.db = db

    # Password operations

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password using bcrypt.

        Args:
            password: Plain text password

        Returns:
            Hashed password string
        """
        return pwd_context.hash(password)

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash.

        Args:
            plain_password: Plain text password
            hashed_password: Hashed password

        Returns:
            True if password matches, False otherwise
        """
        return pwd_context.verify(plain_password, hashed_password)

    # Token operations

    @staticmethod
    def create_access_token(user_id: str, expires_delta: Optional[timedelta] = None) -> str:
        """Create a JWT access token.

        Args:
            user_id: User ID to encode in token
            expires_delta: Optional custom expiration time

        Returns:
            JWT access token string
        """
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

        to_encode = {
            "sub": user_id,
            "type": "access",
            "exp": expire,
        }

        return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

    @staticmethod
    def create_refresh_token(user_id: str) -> str:
        """Create a JWT refresh token.

        Args:
            user_id: User ID to encode in token

        Returns:
            JWT refresh token string
        """
        expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

        to_encode = {
            "sub": user_id,
            "type": "refresh",
            "exp": expire,
        }

        return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

    @staticmethod
    def decode_token(token: str) -> Optional[dict]:
        """Decode and verify a JWT token.

        Args:
            token: JWT token string

        Returns:
            Decoded token payload or None if invalid
        """
        try:
            payload = jwt.decode(
                token,
                settings.JWT_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM]
            )
            return payload
        except JWTError:
            return None

    # User operations

    def authenticate_user(self, email: str, password: str) -> Optional[User]:
        """Authenticate a user by email and password.

        Args:
            email: User email
            password: Plain text password

        Returns:
            User object if authenticated, None otherwise
        """
        user = self.db.query(User).filter(User.email == email).first()

        if not user:
            return None

        if not self.verify_password(password, user.hashed_password):
            return None

        return user

    def create_user(
        self,
        email: str,
        username: str,
        password: str
    ) -> User:
        """Create a new user.

        Args:
            email: User email
            username: Username
            password: Plain text password

        Returns:
            Created User object
        """
        hashed_password = self.hash_password(password)

        user = User(
            email=email,
            username=username,
            hashed_password=hashed_password,
            is_active=True,
            is_verified=False,
        )

        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)

        return user

    def get_user_by_id(self, user_id: str) -> Optional[User]:
        """Get a user by ID.

        Args:
            user_id: User ID

        Returns:
            User object or None
        """
        return self.db.query(User).filter(User.id == user_id).first()

    def get_user_by_email(self, email: str) -> Optional[User]:
        """Get a user by email.

        Args:
            email: User email

        Returns:
            User object or None
        """
        return self.db.query(User).filter(User.email == email).first()

    def get_user_by_username(self, username: str) -> Optional[User]:
        """Get a user by username.

        Args:
            username: Username

        Returns:
            User object or None
        """
        return self.db.query(User).filter(User.username == username).first()

    def update_last_login(self, user: User) -> None:
        """Update user's last login timestamp.

        Args:
            user: User object to update
        """
        user.last_login_at = datetime.utcnow()
        self.db.commit()

    def change_password(self, user: User, new_password: str) -> None:
        """Change a user's password.

        Args:
            user: User object
            new_password: New plain text password
        """
        user.hashed_password = self.hash_password(new_password)
        self.db.commit()

    def update_profile(
        self,
        user: User,
        email: Optional[str] = None,
        username: Optional[str] = None
    ) -> User:
        """Update user profile information.

        Args:
            user: User object to update
            email: New email (optional)
            username: New username (optional)

        Returns:
            Updated User object

        Raises:
            ValueError: If email or username is already taken by another user
        """
        if email and email != user.email:
            existing = self.db.query(User).filter(
                User.email == email,
                User.id != user.id
            ).first()
            if existing:
                raise ValueError("Email already registered")
            user.email = email

        if username and username != user.username:
            existing = self.db.query(User).filter(
                User.username == username,
                User.id != user.id
            ).first()
            if existing:
                raise ValueError("Username already taken")
            user.username = username

        self.db.commit()
        self.db.refresh(user)
        return user

    # Session management

    @staticmethod
    def hash_token(token: str) -> str:
        """Create SHA256 hash of a token.

        Args:
            token: Token string to hash

        Returns:
            Hex digest of SHA256 hash
        """
        return hashlib.sha256(token.encode()).hexdigest()

    def create_session(
        self,
        user_id: str,
        refresh_token: str,
        device_info: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> Session:
        """Create a new session for a user.

        Args:
            user_id: User ID
            refresh_token: The refresh token (will be hashed)
            device_info: User agent string
            ip_address: Client IP address

        Returns:
            Created Session object
        """
        token_hash = self.hash_token(refresh_token)

        session = Session(
            user_id=user_id,
            token_hash=token_hash,
            device_info=device_info,
            ip_address=ip_address,
            is_active=True
        )

        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)

        return session

    def get_user_sessions(self, user_id: str) -> List[Session]:
        """Get all active sessions for a user.

        Args:
            user_id: User ID

        Returns:
            List of active Session objects
        """
        return self.db.query(Session).filter(
            Session.user_id == user_id,
            Session.is_active == True
        ).order_by(Session.last_activity.desc()).all()

    def get_session_by_token(self, refresh_token: str) -> Optional[Session]:
        """Get session by refresh token.

        Args:
            refresh_token: The refresh token

        Returns:
            Session object or None
        """
        token_hash = self.hash_token(refresh_token)
        return self.db.query(Session).filter(
            Session.token_hash == token_hash,
            Session.is_active == True
        ).first()

    def update_session_activity(self, session: Session) -> None:
        """Update session's last activity timestamp.

        Args:
            session: Session object to update
        """
        session.last_activity = datetime.utcnow()
        self.db.commit()

    def revoke_session(self, session_id: str, user_id: str) -> bool:
        """Revoke a specific session.

        Args:
            session_id: Session ID to revoke
            user_id: User ID (for ownership verification)

        Returns:
            True if session was revoked, False if not found
        """
        session = self.db.query(Session).filter(
            Session.id == session_id,
            Session.user_id == user_id,
            Session.is_active == True
        ).first()

        if not session:
            return False

        session.is_active = False
        self.db.commit()
        return True

    def revoke_all_sessions(self, user_id: str, except_session_id: Optional[str] = None) -> int:
        """Revoke all sessions for a user.

        Args:
            user_id: User ID
            except_session_id: Optional session ID to exclude (keep current session)

        Returns:
            Number of sessions revoked
        """
        query = self.db.query(Session).filter(
            Session.user_id == user_id,
            Session.is_active == True
        )

        if except_session_id:
            query = query.filter(Session.id != except_session_id)

        sessions = query.all()
        count = len(sessions)

        for session in sessions:
            session.is_active = False

        self.db.commit()
        return count
