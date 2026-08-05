"""
Root conftest: inject dummy env vars before any app module is imported.
This allows tests to import production code without a live database, MinIO, or Redis.

Set at MODULE level, not inside `pytest_configure` -- pytest loads every
conftest.py (running their top-level code) BEFORE it calls any
`pytest_configure` hook. `tests/conftest.py` does `from app.main import app`
at module level, which needs these vars immediately; a `pytest_configure`
hook here would run too late to satisfy that import in a shell that doesn't
already have them set some other way.
"""
import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("MINIO_ACCESS_KEY", "minioadmin")
os.environ.setdefault("MINIO_SECRET_KEY", "minioadmin")
os.environ.setdefault("SECRET_KEY", "test-secret-key-32-chars-minimum!")
os.environ.setdefault("SONIA_BOT_SECRET", "test-bot-secret")
