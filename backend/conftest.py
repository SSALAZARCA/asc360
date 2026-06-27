"""
Root conftest: inject dummy env vars before any app module is imported.
This allows tests to import production code without a live database, MinIO, or Redis.
"""
import os


def pytest_configure(config):
    os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
    os.environ.setdefault("MINIO_ACCESS_KEY", "minioadmin")
    os.environ.setdefault("MINIO_SECRET_KEY", "minioadmin")
    os.environ.setdefault("SECRET_KEY", "test-secret-key-32-chars-minimum!")
    os.environ.setdefault("SONIA_BOT_SECRET", "test-bot-secret")
