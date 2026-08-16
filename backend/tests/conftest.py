from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.clock import utcnow
from app.db import Base, get_session
from app.main import app
from app.models import Word


@pytest.fixture
def db_session(tmp_path) -> Iterator[Session]:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        yield session
    engine.dispose()


@pytest.fixture
def client(db_session: Session) -> Iterator[TestClient]:
    def override() -> Iterator[Session]:
        try:
            yield db_session
            db_session.commit()
        except Exception:
            db_session.rollback()
            raise

    app.dependency_overrides[get_session] = override
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


VOCABULARY = [
    ("outsider", "посторонний"),
    ("outside", "снаружи"),
    ("outstanding", "выдающийся"),
    ("outcome", "результат"),
    ("chill-out", "расслабляться"),
    ("go after", "преследовать"),
    ("budge", "сдвинуть с места"),
    ("brink", "край"),
    ("tireless", "неутомимый"),
    ("scrutiny", "тщательное изучение"),
    ("salvage", "спасение"),
    ("dandelion", "одуванчик"),
]


@pytest.fixture
def words(db_session: Session) -> list[Word]:
    now = utcnow()
    items = [
        Word(word=w, word_key=w, translation=t, created_at=now) for w, t in VOCABULARY
    ]
    db_session.add_all(items)
    db_session.commit()
    return items
