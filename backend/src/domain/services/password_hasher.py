"""
Password hasher interface (Port).

The algorithm is an infrastructure concern (currently bcrypt via passlib), but
the application layer needs to hash new passwords. Depending on this interface
keeps that dependency pointing inwards.
"""

from abc import ABC, abstractmethod


class IPasswordHasher(ABC):
    """Abstract password hashing service."""

    @abstractmethod
    def hash(self, plain_password: str) -> str:
        """Return a one-way hash suitable for storage."""
        ...

    @abstractmethod
    def verify(self, plain_password: str, password_hash: str) -> bool:
        """Check a candidate password against a stored hash."""
        ...
