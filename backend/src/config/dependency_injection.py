"""
Dependency Injection container.
Wires domain interfaces to infrastructure implementations.
Used for overriding dependencies in tests and different environments.
"""

from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession

from src.application.ports.file_storage import IFileStorage
from src.config.settings import settings
from src.domain.repositories.user_repository import IUserRepository
from src.infrastructure.database.repositories.user_repository_impl import (
    UserRepositoryImpl,
)
from src.infrastructure.security.auth_manager import AuthManager
from src.infrastructure.security.jwt_provider import JWTProvider


class Container:
    """
    Simple DI container for managing service instances.
    In production, consider dependency-injector library for more complex graphs.
    """

    @staticmethod
    def get_jwt_provider() -> JWTProvider:
        return JWTProvider()

    @staticmethod
    @lru_cache(maxsize=1)
    def get_file_storage() -> IFileStorage:
        """
        The process-wide file storage adapter.

        `STORAGE_BACKEND` selects it: `s3` stores in the bucket, `local` (the
        default) writes under `UPLOAD_DIR/files`. Services depend on the
        `IFileStorage` port, so switching backends is this one registration.

        Cached to a single instance because the S3 backend's boto3 client is
        costly to build and safe to reuse across threads; the adapter holds no
        per-request state, so `lru_cache` is enough and leaks nothing between
        requests. The boto3 import stays inside the `s3` branch so the `local`
        backend never requires the dependency to be installed.
        """
        if settings.STORAGE_BACKEND == "local":
            from src.infrastructure.external.storage.local_file_storage import (
                LocalFileStorage,
            )

            return LocalFileStorage(settings.storage_root / "files")

        from src.infrastructure.external.storage.s3_file_storage import (
            S3FileStorage,
            S3StorageConfig,
            build_s3_client,
        )

        config = S3StorageConfig(
            bucket=settings.S3_BUCKET,
            region=settings.S3_REGION,
            access_key=settings.S3_ACCESS_KEY_ID,
            secret_key=settings.S3_SECRET_ACCESS_KEY.get_secret_value(),
            endpoint_url=settings.S3_ENDPOINT_URL,
            key_prefix=settings.S3_KEY_PREFIX,
            ca_bundle=settings.S3_CA_BUNDLE,
            addressing_style=settings.S3_ADDRESSING_STYLE,
            checksum_mode=settings.S3_CHECKSUM_MODE,
            presign_expiry_seconds=settings.S3_PRESIGN_EXPIRY_SECONDS,
        )
        return S3FileStorage(build_s3_client(config), config)

    @staticmethod
    def get_user_repository(session: AsyncSession) -> IUserRepository:
        return UserRepositoryImpl(session)

    @staticmethod
    def get_auth_manager(
        user_repo: IUserRepository,
        jwt_provider: JWTProvider,
    ) -> AuthManager:
        return AuthManager(user_repository=user_repo, jwt_provider=jwt_provider)
