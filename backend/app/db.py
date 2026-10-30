from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

# Sync endpoints run in uvicorn's thread pool (40 threads) and some hold a session while they
# wait on a model call, so the pool must be wide enough for that many at once and must fail
# fast rather than queue for 30 s and take the health check down with it.
engine = create_engine(settings.database_url, pool_pre_ping=True, pool_size=20, max_overflow=30, pool_timeout=10)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session
