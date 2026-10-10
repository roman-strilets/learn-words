"""Отбор записей словаря колоды (слов или фраз) по фильтрам.

Один и тот же отбор нужен списку слов (`GET /words`) и автоматической
разметке (`POST /labels/classify`): пользователь открывает разметку с
фильтрами «Словаря» и ждёт, что «Без меток» + «Изучается» там значат то же
самое, что в списке. Одна функция не даёт определениям разойтись.
"""

from __future__ import annotations

from sqlalchemy import Select, exists, func, or_, select

from app.decks import WORDS, Deck
from app.models import Phrase, Word, WordStatus


class WordFilterError(ValueError):
    """Неизвестное значение фильтра. HTTP-код выбирает роутер."""


def filtered_words(
    *,
    search: str | None,
    status: str | None,
    priority: bool | None,
    label: str | None,
    from_id: int | None = None,
    deck: Deck = WORDS,
) -> Select[tuple[Word | Phrase]]:
    """Запрос слов под фильтрами «Словаря», без сортировки и пагинации.

    `label` — id метки или `none` (слова без меток). `from_id` — только записи
    с `id ≥ from_id`: курсор разметки, который не сдвигается, когда слова
    получают метки и выпадают из фильтра «Без меток».
    """
    Item, Prog, links = deck.item, deck.progress, deck.links
    link_item_id = deck.link_item_id
    stmt = select(Item).outerjoin(Prog, Prog.word_id == Item.id)

    if search:
        pattern = f"%{search.strip().lower()}%"
        stmt = stmt.where(
            or_(func.lower(Item.word).like(pattern), func.lower(Item.translation).like(pattern))
        )

    if status == "new":
        stmt = stmt.where(Prog.word_id.is_(None))
    elif status:
        if status not in {s.value for s in WordStatus}:
            raise WordFilterError("Неизвестный статус")
        stmt = stmt.where(Prog.status == status)

    if priority:
        stmt = stmt.where(Item.priority.is_(True))

    if label == "none":
        stmt = stmt.where(~exists().where(link_item_id == Item.id))
    elif label:
        if not label.isdigit():
            raise WordFilterError("Неизвестная метка")
        stmt = stmt.where(
            exists().where(link_item_id == Item.id, links.c.label_id == int(label))
        )

    if from_id is not None:
        stmt = stmt.where(Item.id >= from_id)

    return stmt


def count_rows(stmt: Select) -> Select[tuple[int]]:
    """`COUNT` по запросу отбора — для `total` списка и `remaining` разметки."""
    return select(func.count()).select_from(stmt.subquery())
