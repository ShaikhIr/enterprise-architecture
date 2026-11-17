"""
Password hasher implementation (Adapter).

Thin wrapper over the existing bcrypt helpers so the application layer can
depend on IPasswordHasher instead of importing infrastructure directly.
"""

from src.domain.services.password_hasher import IPasswordHasher
from src.infrastructure.security.password_encoder import hash_password, verify_password


class BcryptPasswordHasher(IPasswordHasher):
    """Bcrypt-backed password hashing."""

    def hash(self, plain_password: str) -> str:
        return hash_password(plain_password)

    def verify(self, plain_password: str, password_hash: str) -> bool:
        return verify_password(plain_password, password_hash)
