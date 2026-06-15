"""
Role-Based Access Control (RBAC) manager.
Provides role validation and endpoint protection via FastAPI dependencies.
"""

from enum import StrEnum
from functools import wraps
from typing import Any, Callable

from fastapi import Depends, HTTPException, status

from src.domain.entities.user import User


class Role(StrEnum):
    """System roles ordered by privilege level."""

    ADMIN = "ADMIN"
    MANAGER = "MANAGER"
    USER = "USER"


# Role hierarchy: higher roles include permissions of lower roles
ROLE_HIERARCHY: dict[Role, int] = {
    Role.ADMIN: 1,
    Role.MANAGER: 2,
    Role.USER: 3,
}


def has_minimum_role(user_role: str, required_role: str) -> bool:
    """Check if user's role meets or exceeds the required role level."""
    user_level = ROLE_HIERARCHY.get(Role(user_role), 0)
    required_level = ROLE_HIERARCHY.get(Role(required_role), 0)
    return user_level >= required_level


class RBACManager:
    """Provides role-based authorization checks."""

    @staticmethod
    def require_role(required_role: str) -> Callable:
        """
        FastAPI dependency factory for role-based endpoint protection.

        Usage:
            @router.get("/admin", dependencies=[Depends(RBACManager.require_role("ADMIN"))])
            async def admin_only():
                ...
        """

        async def role_checker(current_user: User) -> User:
            if not has_minimum_role(current_user.role, required_role):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Role '{required_role}' or higher required",
                )
            return current_user

        return role_checker


def require_role(required_role: str) -> Callable:
    """
    Decorator for protecting endpoint functions with role checks.

    Usage:
        @router.get("/users")
        @require_role("ADMIN")
        async def list_users(current_user: User = Depends(get_current_active_user)):
            ...
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Extract current_user from kwargs (injected by FastAPI DI)
            current_user: User | None = kwargs.get("current_user")
            if current_user is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required",
                )
            if not has_minimum_role(current_user.role, required_role):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Role '{required_role}' or higher required",
                )
            return await func(*args, **kwargs)

        return wrapper

    return decorator
