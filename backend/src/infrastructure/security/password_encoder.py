"""
Password hashing and verification using BCrypt.
Provides secure one-way hashing for user passwords.
"""

from passlib.context import CryptContext

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    """Hash a plain-text password using BCrypt."""
    return _pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain-text password against a BCrypt hash."""
    return _pwd_context.verify(plain_password, hashed_password)
