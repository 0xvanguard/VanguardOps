"""Shared test fixtures.

Architecture
------------
* A single SQLite engine is built once per *session* and the schema is
  created on first use.
* For every test, we open a fresh connection, start a transaction, bind a
  scoped session to it, and roll back on teardown. Tests never see each
  other's data, so order-independence is guaranteed.
* The FastAPI ``get_db`` dependency is overridden to yield the
  per-test session, so endpoints, services and CRUD all hit the same
  in-memory state and respect the rollback.
* Auth fixtures issue real JWT tokens from real DB users (admin /
  operator / viewer), exercising the full RBAC path on every request.
"""

from __future__ import annotations

# Configure environment BEFORE importing the application so settings pick
# up the test values (the ``Settings`` instance is cached at import-time).
import os
import pathlib
import sys

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ.setdefault("LOG_FORMAT", "console")
os.environ.setdefault(
    "SECRET_KEY",
    "test-secret-key-must-be-at-least-thirty-two-characters-long",
)
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("CELERY_BROKER_URL", "memory://")
os.environ.setdefault("CELERY_RESULT_BACKEND", "cache+memory://")
os.environ.setdefault("CELERY_TASK_ALWAYS_EAGER", "true")
# Rate limiting is intentionally LEFT ENABLED in tests so the middleware's
# behaviour is exercised on every test run; the per-test FakeRedis fixture
# resets state between tests, and default per-IP limits (100/min) are well
# above what any test method emits.

# Ensure the repo root is importable when running ``pytest`` from any cwd.
ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from collections.abc import Generator  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app.api.deps import get_db  # noqa: E402
from app.core.security import Role, create_access_token  # noqa: E402
from app.database import Base  # noqa: E402
from app.main import create_app  # noqa: E402
from app.services.ip_banlist import IPBanlist, set_banlist  # noqa: E402
from app.services.rate_limiter import SlidingWindowRateLimiter, set_rate_limiter  # noqa: E402
from app.services.token_blacklist import TokenBlacklist, set_blacklist  # noqa: E402
from tests._fakes import FakeRedis  # noqa: E402
from tests.factories import (  # noqa: E402
    AssetFactory,
    TicketFactory,
    UserFactory,
    WorkflowFactory,
    register_session,
)

# ---------------------------------------------------------------------------
# Engine & schema (session scope)
# ---------------------------------------------------------------------------

TEST_DB_URL = "sqlite:///:memory:"

# StaticPool keeps a single shared in-memory database across connections,
# which is required for the rollback-per-test pattern to see the same data.
from sqlalchemy.pool import StaticPool  # noqa: E402

engine = create_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
    future=True,
)


@pytest.fixture(scope="session", autouse=True)
def _create_schema() -> Generator[None, None, None]:
    """Create all tables once per test session."""
    # Import models so all tables are registered on the metadata.
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


# ---------------------------------------------------------------------------
# Per-test session with transactional rollback
# ---------------------------------------------------------------------------


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Yield a SQLAlchemy session whose changes are rolled back at teardown.

    The pattern uses a single connection, a top-level transaction, and a
    SAVEPOINT-based nested transaction that we restart on every commit
    inside the test - this lets the application code call ``db.commit()``
    naturally while still discarding everything when the test ends.
    """
    connection = engine.connect()
    transaction = connection.begin()
    test_session_factory = sessionmaker(bind=connection, autoflush=False, future=True)
    session = test_session_factory()

    # Mirror production: when the app calls ``commit``, restart the
    # SAVEPOINT so subsequent statements stay inside the outer transaction.
    nested = connection.begin_nested()

    from sqlalchemy import event

    @event.listens_for(session, "after_transaction_end")
    def _restart_savepoint(sess, trans):  # pragma: no cover - SQLA hook
        nonlocal nested
        if trans.nested and not trans._parent.nested:
            nested = connection.begin_nested()

    # Make factories use this session by default.
    register_session(session)

    try:
        yield session
    finally:
        session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()


# ---------------------------------------------------------------------------
# JWT blacklist (FakeRedis injected per test)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def fake_blacklist() -> Generator[FakeRedis, None, None]:
    """Replace the process-wide blacklist with an in-memory fake.

    Yielding the underlying ``FakeRedis`` lets a test toggle
    ``fail_calls = True`` to exercise the fail-closed / fail-open paths.
    Cleared after every test so revocations from one test do not leak.
    """
    fake = FakeRedis()
    set_blacklist(TokenBlacklist(fake, fallback="closed"))
    try:
        yield fake
    finally:
        set_blacklist(None)


# ---------------------------------------------------------------------------
# Rate limiter + IP banlist (FakeRedis injected per test)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def fake_security_redis() -> Generator[FakeRedis, None, None]:
    """Replace the rate limiter and IP banlist with in-memory fakes.

    Both share the same FakeRedis instance so a test can assert end-to-end
    interactions (e.g. ``track_auth_failure`` -> ban activated) without
    juggling two separate stores.
    """
    fake = FakeRedis()
    set_rate_limiter(SlidingWindowRateLimiter(fake, fail_open=True))
    set_banlist(
        IPBanlist(
            fake,
            # Tighter thresholds in tests so we can hit them cheaply without
            # generating thousands of requests.
            auth_failure_threshold=5,
            auth_failure_window=60,
            scan_threshold=5,
            scan_window=60,
        )
    )
    try:
        yield fake
    finally:
        set_rate_limiter(None)
        set_banlist(None)


# ---------------------------------------------------------------------------
# FastAPI TestClient with overridden DB dependency
# ---------------------------------------------------------------------------


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """Yield a TestClient that uses the per-test rolled-back session."""
    app = create_app()

    def _override_get_db() -> Generator[Session, None, None]:
        try:
            yield db_session
        finally:
            # Don't close - the outer fixture owns the lifecycle.
            pass

    app.dependency_overrides[get_db] = _override_get_db

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Users + JWT helpers
# ---------------------------------------------------------------------------


def _make_token(user_id: int, role: Role) -> str:
    return create_access_token(subject=user_id, role=role)


@pytest.fixture
def admin_user(db_session: Session):
    return UserFactory(role=Role.ADMIN)


@pytest.fixture
def operator_user(db_session: Session):
    return UserFactory(role=Role.OPERATOR)


@pytest.fixture
def viewer_user(db_session: Session):
    return UserFactory(role=Role.VIEWER)


@pytest.fixture
def admin_token(admin_user) -> str:
    return _make_token(admin_user.id, Role.ADMIN)


@pytest.fixture
def operator_token(operator_user) -> str:
    return _make_token(operator_user.id, Role.OPERATOR)


@pytest.fixture
def viewer_token(viewer_user) -> str:
    return _make_token(viewer_user.id, Role.VIEWER)


@pytest.fixture
def admin_headers(admin_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def operator_headers(operator_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {operator_token}"}


@pytest.fixture
def viewer_headers(viewer_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {viewer_token}"}


# Re-export factories for convenience in tests.
__all__ = [
    "AssetFactory",
    "TicketFactory",
    "UserFactory",
    "WorkflowFactory",
]
