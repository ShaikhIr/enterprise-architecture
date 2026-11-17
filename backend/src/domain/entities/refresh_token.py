"""
RefreshToken domain entity.

The server-side record of one issued refresh token. The token itself is a signed JWT the
client holds; this row is what makes it revocable and single-use. Every token descended from
one login shares a `family_id`, so a stolen-and-replayed token can end the whole session.
"""

from dataclasses import dataclass, field
from datetime import datetime

from src.domain.entities.base_entity import BaseEntity


@dataclass(kw_only=True)
class RefreshToken(BaseEntity):
    """One issued refresh token, identified by the JWT's `jti` claim."""

    jti: str = field(default="")
    family_id: str = field(default="")
    user_id: int = field(default=0)
    expires_at: datetime
    # Set the moment the token is exchanged for a new one. A token is single-use.
    used_at: datetime | None = field(default=None)
    # Set when the session is ended (logout, or reuse of a spent token was detected).
    revoked_at: datetime | None = field(default=None)
