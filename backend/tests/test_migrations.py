"""Миграции фраз и занятия по группе поверх базы со словами: слова, прогресс и
журнал не меняются.

Остальные тесты строят схему через `create_all`, поэтому сами миграции
проверяются только здесь — настоящим `alembic upgrade` на временном файле.
"""

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from alembic import command
from app.config import BACKEND_DIR, settings

PHRASES_REVISION = "31a578309216"

PHRASE_TABLES = {
    "phrases",
    "phrase_progress",
    "phrase_review_log",
    "phrase_labels",
    "phrase_label_links",
}


@pytest.fixture
def alembic_db(tmp_path, monkeypatch):
    """Пустой файл SQLite и конфиг Alembic, нацеленный на него.

    `alembic/env.py` берёт адрес из `settings.database_url` при каждом запуске
    команды, так что достаточно подменить его на живом объекте настроек.
    """
    url = f"sqlite:///{tmp_path / 'migrate.db'}"
    monkeypatch.setattr(settings, "database_url", url)
    # Без `alembic.ini`: env.py настраивает логирование по нему, а это
    # перенастроило бы логирование всего прогона pytest
    config = Config()
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    engine = create_engine(url)
    yield config, engine
    engine.dispose()


def _seed_word(engine) -> None:
    # Строкой, как её пишет SQLAlchemy: адаптер datetime в sqlite3 устарел
    moment = "2026-09-01 12:00:00.000000"
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO words (id, word, word_key, translation, created_at, priority) "
                "VALUES (1, 'budge', 'budge', 'сдвинуть с места', :t, 0)"
            ),
            {"t": moment},
        )
        conn.execute(
            text(
                "INSERT INTO progress (word_id, status, step, repetitions, ease, "
                "interval_days, due_at, lapses, started_at, updated_at) "
                "VALUES (1, 'review', 0, 3, 2.4, 6.0, :t, 1, :t, :t)"
            ),
            {"t": moment},
        )
        conn.execute(
            text(
                "INSERT INTO review_log (word_id, exercise, correct, answer, used_hint, "
                "attempt, quality, status_before, status_after, ease_after, "
                "interval_after, created_at, session_id) "
                "VALUES (1, 'letters', 1, 'budge', 0, 1, 5, 'review', 'review', 2.4, "
                "6.0, :t, 's-1')"
            ),
            {"t": moment},
        )


def _word_snapshot(engine) -> tuple:
    with engine.connect() as conn:
        return (
            conn.execute(text("SELECT * FROM words")).all(),
            conn.execute(text("SELECT * FROM progress")).all(),
            conn.execute(text("SELECT * FROM review_log")).all(),
        )


def test_phrase_migration_keeps_words(alembic_db) -> None:
    config, engine = alembic_db

    # База со словами — до фраз
    command.upgrade(config, "f59f358ade34")
    _seed_word(engine)
    before = _word_snapshot(engine)
    assert not PHRASE_TABLES & set(inspect(engine).get_table_names())

    # Ревизия фраз, а не `head`: поверх неё есть миграции, и откат на шаг
    # от `head` убрал бы уже не фразы
    command.upgrade(config, PHRASES_REVISION)
    assert PHRASE_TABLES <= set(inspect(engine).get_table_names())
    assert _word_snapshot(engine) == before

    # Откат убирает только таблицы фраз
    command.downgrade(config, "-1")
    assert not PHRASE_TABLES & set(inspect(engine).get_table_names())
    assert _word_snapshot(engine) == before

    command.upgrade(config, PHRASES_REVISION)
    assert PHRASE_TABLES <= set(inspect(engine).get_table_names())
    assert _word_snapshot(engine) == before
    assert len(before[0]) == len(before[1]) == len(before[2]) == 1


GROUP_TABLES = {"group_cycle_words", "group_review_log"}


def _seed_label(engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO labels (id, name, name_key, created_at) "
                "VALUES (1, 'кухня', 'кухня', '2026-09-01 12:00:00.000000')"
            )
        )
        conn.execute(text("INSERT INTO word_labels (word_id, label_id) VALUES (1, 1)"))


def _labels_snapshot(engine) -> tuple:
    with engine.connect() as conn:
        return (
            conn.execute(text("SELECT * FROM labels")).all(),
            conn.execute(text("SELECT * FROM word_labels")).all(),
        )


def test_group_study_migration_keeps_words(alembic_db) -> None:
    config, engine = alembic_db

    command.upgrade(config, PHRASES_REVISION)
    _seed_word(engine)
    _seed_label(engine)
    before = (_word_snapshot(engine), _labels_snapshot(engine))
    assert not GROUP_TABLES & set(inspect(engine).get_table_names())

    command.upgrade(config, "head")
    inspector = inspect(engine)
    assert GROUP_TABLES <= set(inspector.get_table_names())
    assert {c["name"] for c in inspector.get_columns("group_cycle_words")} == {
        "label_id",
        "cycle",
        "word_id",
        "position",
        "done_at",
        "done_session_id",
    }
    assert {c["name"] for c in inspector.get_columns("group_review_log")} == {
        "id",
        "word_id",
        "label_id",
        "exercise",
        "correct",
        "answer",
        "used_hint",
        "attempt",
        "quality",
        "duration_ms",
        "session_id",
        "created_at",
    }
    assert (_word_snapshot(engine), _labels_snapshot(engine)) == before

    # Откат убирает только таблицы группы: фразы и слова на месте
    command.downgrade(config, "-1")
    tables = set(inspect(engine).get_table_names())
    assert not GROUP_TABLES & tables
    assert PHRASE_TABLES <= tables
    assert (_word_snapshot(engine), _labels_snapshot(engine)) == before
