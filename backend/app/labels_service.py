"""Метки слов: ключ названия, порядок и список со счётчиками.

Метки — ручная разметка словаря. К занятиям и расписанию они отношения не
имеют, поэтому живут отдельно от `study_service.py`.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.classifier import Classifier, LabelItem, WordItem
from app.models import Label, Word, word_labels
from app.schemas import ClassifyBatch, ClassifyRequest, ClassifyResult, LabelOut, LabelRef
from app.word_filters import count_rows, filtered_words


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
    return [label_out(label, count) for label, count in rows]


def label_out(label: Label, count: int) -> LabelOut:
    return LabelOut(
        id=label.id, name=label.name, description=label.description, word_count=count
    )


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


class NoLabelsError(ValueError):
    """В наборе разметки не осталось ни одной существующей метки."""


def classify_batch(
    session: Session, request: ClassifyRequest, classifier: Classifier
) -> ClassifyBatch:
    """Разметить одну пачку: каждому слову — выбранная моделью метка или ничего.

    Метки только добавляются, ни одна не снимается. `progress` и `review_log`
    не трогаются: разметка — правка словаря, а не ответ на упражнение.
    Пачка применяется целиком или никак: ошибка классификатора случается до
    любой записи, а его исключения переводит в ответ роутер.
    """
    labels = session.scalars(select(Label).where(Label.id.in_(request.label_ids))).all()
    if not labels:
        raise NoLabelsError("Нет меток для разметки")

    def selection(from_id: int | None):
        return filtered_words(
            search=request.search,
            status=request.status,
            priority=request.priority,
            label=request.label,
            from_id=from_id,
        )

    words = session.scalars(
        selection(request.from_id).order_by(Word.id).limit(request.limit)
    ).all()
    if not words:
        return ClassifyBatch(results=[], skipped=0, next_from_id=None, remaining=0)

    word_items = [WordItem(id=w.id, word=w.word, translation=w.translation) for w in words]
    label_items = [
        LabelItem(id=label.id, name=label.name, description=label.description)
        for label in labels
    ]
    # Модель думает до двух минут. Открытая всё это время транзакция чтения в
    # WAL держала бы старый снимок, и запись после чужой записи (правка слова
    # во второй вкладке) упала бы с SQLITE_BUSY_SNAPSHOT
    session.commit()

    choices = classifier.classify(word_items, label_items)

    # Пока модель думала, слово или метку могли удалить, а метку — поставить
    # вручную: решение принимается по свежему состоянию
    session.expire_all()
    fresh_words = {
        w.id: w
        for w in session.scalars(select(Word).where(Word.id.in_([i.id for i in word_items])))
    }
    fresh_labels = {
        label.id: label
        for label in session.scalars(
            select(Label).where(Label.id.in_([i.id for i in label_items]))
        )
    }

    results: list[ClassifyResult] = []
    skipped = 0
    for item in word_items:
        word = fresh_words.get(item.id)
        if word is None:
            skipped += 1
            continue
        label_id = choices.get(item.id)
        label = fresh_labels.get(label_id) if label_id is not None else None
        added = label is not None and label not in word.labels
        if added:
            word.labels.append(label)
        results.append(
            ClassifyResult(
                word_id=word.id,
                word=word.word,
                translation=word.translation,
                label=LabelRef(id=label.id, name=label.name) if label is not None else None,
                added=added,
            )
        )
    session.flush()

    # Курсор по `id`, а не смещение: слова, получившие метку, выпадают из
    # фильтра «Без меток», но они уже позади курсора и ничего не сдвигают
    next_from_id = word_items[-1].id + 1
    remaining = session.scalar(count_rows(selection(next_from_id))) or 0
    return ClassifyBatch(
        results=results,
        skipped=skipped,
        next_from_id=next_from_id if remaining else None,
        remaining=remaining,
    )
