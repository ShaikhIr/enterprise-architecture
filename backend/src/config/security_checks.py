"""
Startup checks for security-critical settings.

A deployment that forgets to override the JWT signing key would sign every token with a string
that is public in this repository, letting anyone mint a valid admin token. That is not a
misconfiguration to warn about and carry on from: the process refuses to start. Local
development opts out with DEBUG=true.
"""

from src.config.settings import Settings
from src.observability.structured_logger import get_logger

# Every value that ships in this repository as an example. None is a secret.
KNOWN_PLACEHOLDER_SECRETS: frozenset[str] = frozenset(
    {
        "change-me-in-production-use-strong-secret",
        "your-super-secret-key-change-in-production",
    }
)
MIN_JWT_SECRET_LENGTH = 32


class InsecureConfigurationError(RuntimeError):
    """Raised at startup when a setting would leave the deployment trivially breakable."""


def validate_security_configuration(settings: Settings) -> None:
    """
    Refuse to start with a forgeable JWT key; warn about cookies that travel over plain HTTP.

    With DEBUG=true the key check is skipped, so a developer can run from the example
    `.env` without generating a secret.

    Raises:
        InsecureConfigurationError: JWT_SECRET_KEY is a shipped placeholder or too short,
            and DEBUG is off.
    """
    log = get_logger("security_config")

    if settings.DEBUG:
        log.warning(
            "security_checks_skipped",
            detail="DEBUG is true: JWT_SECRET_KEY and COOKIE_SECURE are not enforced",
        )
        return

    secret = settings.JWT_SECRET_KEY
    if secret in KNOWN_PLACEHOLDER_SECRETS:
        raise InsecureConfigurationError(
            "JWT_SECRET_KEY is still a placeholder from the repository. Set it to a random "
            f"value of at least {MIN_JWT_SECRET_LENGTH} characters "
            '(for example: python -c "import secrets; print(secrets.token_urlsafe(48))"), '
            "or set DEBUG=true for local development."
        )
    if len(secret.encode("utf-8")) < MIN_JWT_SECRET_LENGTH:
        raise InsecureConfigurationError(
            f"JWT_SECRET_KEY is shorter than {MIN_JWT_SECRET_LENGTH} bytes, which makes the "
            "signature guessable offline. Use a longer random value."
        )

    if not settings.COOKIE_SECURE:
        log.warning(
            "cookie_secure_disabled",
            detail=(
                "COOKIE_SECURE is false, so the refresh-token cookie is also sent over plain "
                "HTTP. Set COOKIE_SECURE=true wherever the API is served over HTTPS."
            ),
        )
