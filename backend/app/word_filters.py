"""Отбор слов «Словаря» по фильтрам.

Один и тот же отбор нужен списку слов (`GET /words`) и автоматической
разметке (`POST /labels/classify`): пользователь открывает разметку с
фильтрами «Словаря» и ждёт, что «Без меток» + «Изучается» там значат то же
самое, что в списке. Одна функция не даёт определениям разойтись.
"""

from __future__ import annotations

from sqlalchemy import Select, exists, func, or_, select

from app.models import Progress, Word, WordStatus, word_labels


class WordFilterError(ValueError):
    """Неизвестное значение фильтра. HTTP-код выбирает роутер."""


def filtered_words(
    *,
    search: str | None,
    status: str | None,
    priority: bool | None,
    label: str | None,
    from_id: int | None = None,
) -> Select[tuple[Word]]:
    """Запрос слов под фильтрами «Словаря», без сортировки и пагинации.

    `label` — id метки или `none` (слова без меток). `from_id` — только записи
    с `id ≥ from_id`: курсор разметки, который не сдвигается, когда слова
    получают метки и выпадают из фильтра «Без меток».
    """
    stmt = select(Word).outerjoin(Progress, Progress.word_id == Word.id)

    if search:
        pattern = f"%{search.strip().lower()}%"
        stmt = stmt.where(
            or_(func.lower(Word.word).like(pattern), func.lower(Word.translation).like(pattern))
        )

    if status == "new":
        stmt = stmt.where(Progress.word_id.is_(None))
    elif status:
        if status not in {s.value for s in WordStatus}:
            raise WordFilterError("Неизвестный статус")
        stmt = stmt.where(Progress.status == status)

    if priority:
        stmt = stmt.where(Word.priority.is_(True))

    if label == "none":
        stmt = stmt.where(~exists().where(word_labels.c.word_id == Word.id))
    elif label:
        if not label.isdigit():
            raise WordFilterError("Неизвестная метка")
        stmt = stmt.where(
            exists().where(
                word_labels.c.word_id == Word.id, word_labels.c.label_id == int(label)
            )
        )

    if from_id is not None:
        stmt = stmt.where(Word.id >= from_id)

    return stmt


def count_rows(stmt: Select) -> Select[tuple[int]]:
    """`COUNT` по запросу отбора — для `total` списка и `remaining` разметки."""
    return select(func.count()).select_from(stmt.subquery())
