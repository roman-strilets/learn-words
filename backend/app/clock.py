"""Единая точка получения текущего времени.

В базе хранится naive UTC: SQLite не умеет часовые пояса, а смешивание
aware/naive datetime — источник трудноуловимых багов. Все функции SRS
принимают `now` параметром, чтобы их можно было тестировать без подмены времени.
"""

from datetime import UTC, datetime


def utcnow() -> datetime:
    """Текущее время UTC без tzinfo."""
    return datetime.now(UTC).replace(tzinfo=None)
