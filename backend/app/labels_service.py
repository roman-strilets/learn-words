"""Метки слов: ключ названия, порядок и список со счётчиками.

Метки — ручная разметка словаря. К занятиям и расписанию они отношения не
имеют, поэтому живут отдельно от `study_service.py`.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Label, word_labels
from app.schemas import LabelOut


def label_key(name: str) -> str:
    """Ключ уникальности названия.

    Считается в Python: `lower()` в SQLite не знает кириллицы, а «Кухня» и
    «кухня» должны быть одной меткой.
    """
    return name.strip().casefold()


def label_sort_key(key: str) -> str:
    """Ключ сортировки меток по алфавиту.

    Без замены «ё» ушла бы в конец, после «я». В UTF-8 «а–п» (`D0 B0…BF`)
    идут перед «р–я» (`D1 80…8F`), поэтому побайтовое сравнение SQLite после
    той же замены даёт тот же порядок — на этом стоит `order_by` у `Word.labels`.
    """
    return key.replace("ё", "е")


def list_labels(session: Session) -> list[LabelOut]:
    """Все метки по алфавиту с числом слов у каждой."""
    rows = session.execute(
        select(Label, func.count(word_labels.c.word_id))
        .outerjoin(word_labels, word_labels.c.label_id == Label.id)
        .group_by(Label.id)
    ).all()
    rows.sort(key=lambda row: label_sort_key(row[0].name_key))
    return [LabelOut(id=label.id, name=label.name, word_count=count) for label, count in rows]


def resolve_labels(session: Session, names: list[str]) -> list[Label]:
    """Метки по названиям из формы слова: существующие берутся, недостающие создаются.

    Совпадение по ключу берёт существующую метку с её написанием: переименование
    делается только на вкладке «Метки». Повторы в списке схлопываются, первое
    вхождение побеждает. Вызывается в транзакции сохранения слова, поэтому
    отклонённое сохранение новых меток не оставляет.
    """
    wanted: dict[str, str] = {}
    for name in names:
        wanted.setdefault(label_key(name), name.strip())

    found = {
        label.name_key: label
        for label in session.scalars(select(Label).where(Label.name_key.in_(wanted)))
    }
    for key, name in wanted.items():
        if key not in found:
            found[key] = Label(name=name, name_key=key)
            session.add(found[key])

    # Присвоенный `word.labels` уходит в ответ как есть, а `order_by` у связи
    # действует только при загрузке из базы — поэтому сортируем здесь
    return sorted(found.values(), key=lambda label: label_sort_key(label.name_key))


def find_by_key(session: Session, key: str, *, exclude_id: int | None = None) -> Label | None:
    """Метка с тем же ключом названия.

    `exclude_id` — сама переименуемая метка: смена регистра не конфликт.
    """
    stmt = select(Label).where(Label.name_key == key)
    if exclude_id is not None:
        stmt = stmt.where(Label.id != exclude_id)
    return session.scalar(stmt)


def word_count(session: Session, label: Label) -> int:
    """Число слов с меткой."""
    return session.scalar(
        select(func.count()).select_from(word_labels).where(word_labels.c.label_id == label.id)
    ) or 0
