"""Занятие по группе: порция слов одной метки и пять раундов без знакомства.

Связывает чистую логику круга (`app/group_cycles.py`), генератор упражнений
и базу. Правила раундов, проверка ответа и оценка попытки — те же, что у
обычного занятия; расходится только то, что остаётся после занятия.

Сервис НИКОГДА не пишет `progress`, `review_log` и `words.priority` и не читает
прогресс слова: статусы, расписание, «Учить первым», дневной лимит новых и
статистика от занятия по группе не меняются (FR-006–FR-010). Его следы — только
круг группы (`group_cycle_words`) и журнал ответов (`group_review_log`). Это
закрепляют тесты изоляции в `tests/test_group_study_api.py`.

Сборка занятия пишет в базу — заводит строки круга. Это не серверная сессия:
круг — долговременные данные того же рода, что прогресс, и обязан переживать
перезагрузку и другой браузер; очередь занятия по-прежнему живёт на фронте
(research R7).
"""

from __future__ import annotations

import random
import uuid
from collections import defaultdict
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import settings
from app.decks import WORDS
from app.exercises import build_exercise, check_answer, correct_answer_for
from app.group_cycles import CycleEntry, PortionPlan, plan_portion, plan_restart, summary
from app.labels_service import label_sort_key
from app.models import GroupCycleWord, GroupReviewLog, Label, Word, word_labels
from app.schemas import (
    GroupAnswerRequest,
    GroupAnswerResponse,
    GroupFinishResult,
    GroupOut,
    GroupSessionOut,
)
from app.srs import EXERCISE_ROUNDS, EXERCISES_WITHOUT_HINT, derive_quality
from app.study_service import _rounds_for


class WordNotInGroupError(Exception):
    """Со слова сняли метку занятия — отвечать по нему в этой группе нельзя."""


# ------------------------------------------------------------------------ круг


def members(session: Session, label_id: int) -> list[int]:
    """Слова группы — все слова с этой меткой, в любом статусе (FR-019)."""
    stmt = (
        select(word_labels.c.word_id)
        .where(word_labels.c.label_id == label_id)
        .order_by(word_labels.c.word_id)
    )
    return list(session.scalars(stmt))


def _entry(row: GroupCycleWord) -> CycleEntry:
    return CycleEntry(row.word_id, row.cycle, row.position, row.done_at is not None)


def _entries(session: Session, label_id: int) -> list[CycleEntry]:
    rows = session.scalars(select(GroupCycleWord).where(GroupCycleWord.label_id == label_id))
    return [_entry(row) for row in rows]


def _apply(session: Session, label_id: int, plan: PortionPlan) -> None:
    """Записать план круга: старые круги удалить, новые строки добавить."""
    if plan.delete_below is not None:
        session.execute(
            delete(GroupCycleWord).where(
                GroupCycleWord.label_id == label_id,
                GroupCycleWord.cycle < plan.delete_below,
            )
        )
    session.add_all(
        GroupCycleWord(label_id=label_id, cycle=e.cycle, word_id=e.word_id, position=e.position)
        for e in plan.inserts
    )
    session.flush()


def list_groups(session: Session) -> list[GroupOut]:
    """Все метки слов по алфавиту — с размером группы и местом в круге.

    Только чтение: строки круга заводит сборка занятия, а не выбор группы.
    Связки и круги читаются двумя запросами на все метки сразу.
    """
    labels = sorted(session.scalars(select(Label)), key=lambda lbl: label_sort_key(lbl.name_key))

    by_label: dict[int, list[int]] = defaultdict(list)
    for label_id, word_id in session.execute(
        select(word_labels.c.label_id, word_labels.c.word_id)
    ):
        by_label[label_id].append(word_id)

    cycles: dict[int, list[CycleEntry]] = defaultdict(list)
    for row in session.scalars(select(GroupCycleWord)):
        cycles[row.label_id].append(_entry(row))

    groups = []
    for label in labels:
        word_count, done, cycle = summary(by_label[label.id], cycles[label.id])
        groups.append(
            GroupOut(
                label_id=label.id,
                name=label.name,
                word_count=word_count,
                done=done,
                cycle=cycle,
            )
        )
    return groups


# --------------------------------------------------------------------- занятие


def build_group_session(
    session: Session, label: Label, now: datetime, rng: random.Random | None = None
) -> GroupSessionOut:
    """Порция группы и её пять раундов.

    Повтор без `finish` между запросами даёт тот же набор слов: круг и его
    следующий круг хранятся, а порция выводится из них. Порядок слов в раундах
    каждый раз новый — как у повторения. Дневного лимита нет (FR-007).
    """
    rng = rng or random.Random()

    word_ids = members(session, label.id)
    plan = plan_portion(
        word_ids, _entries(session, label.id), settings.group_words_per_session, rng
    )
    _apply(session, label.id, plan)

    words = [word for word_id in plan.word_ids if (word := session.get(Word, word_id))]
    # Дистракторы — из всего словаря, а не только из группы (FR-004a)
    rounds = _rounds_for(session, words, rng, WORDS)
    word_count, done, cycle = summary(word_ids, _entries(session, label.id))

    return GroupSessionOut(
        label_id=label.id,
        name=label.name,
        session_id=str(uuid.uuid4()) if words else None,
        rounds=rounds,
        word_count=word_count,
        done=done,
        cycle=cycle,
    )


def _in_group(session: Session, word_id: int, label_id: int) -> bool:
    stmt = select(word_labels.c.word_id).where(
        word_labels.c.word_id == word_id, word_labels.c.label_id == label_id
    )
    return session.scalar(stmt) is not None


def answer_group_exercise(
    session: Session,
    word: Word,
    label: Label,
    request: GroupAnswerRequest,
    now: datetime,
    rng: random.Random | None = None,
) -> GroupAnswerResponse:
    """Проверить ответ и записать попытку в журнал группы.

    Проверка, оценка и пересборка карточки после ошибки — как у обычного
    занятия. Прогресс слова не читается: в группе бывают и новые слова, а
    ответ здесь расписания не двигает (research R8).
    """
    rng = rng or random.Random()
    if not _in_group(session, word.id, label.id):
        raise WordNotInGroupError

    correct = check_answer(word, request.exercise, request.answer)
    used_hint = request.used_hint and request.exercise not in EXERCISES_WITHOUT_HINT
    quality = derive_quality(correct=correct, used_hint=used_hint, attempt=request.attempt)

    repeat = not correct
    next_exercise = (
        build_exercise(
            session,
            word,
            request.exercise,
            show_letters=True,
            attempt=request.attempt + 1,
            rng=rng,
        )
        if repeat
        else None
    )

    session.add(
        GroupReviewLog(
            word_id=word.id,
            label_id=label.id,
            exercise=request.exercise.value,
            correct=correct,
            answer=request.answer,
            used_hint=used_hint,
            attempt=request.attempt,
            quality=quality,
            duration_ms=request.duration_ms,
            session_id=request.session_id,
            created_at=now,
        )
    )
    session.flush()

    return GroupAnswerResponse(
        correct=correct,
        correct_answer=correct_answer_for(word, request.exercise),
        word=word.word,
        translation=word.translation,
        example=word.example,
        example_translation=word.example_translation,
        quality=quality,
        repeat_in_session=repeat,
        next_exercise=next_exercise,
    )


def finish_group_session(
    session: Session, session_id: str, now: datetime
) -> list[GroupFinishResult]:
    """Отметить пройденными слова, верно ответившие во всех раундах порции.

    Слово закрывает свою самую раннюю непройденную строку круга: слово остатка —
    текущий круг, добранное на стыке — следующий. Ключ занятия в строке делает
    повторный `finish` безвредным: без него он закрыл бы слову ещё и следующий
    круг (research R6). Ошибки на прохождение не влияют (FR-014), не дошедшее
    до конца раундов слово не меняется (FR-016).
    """
    attempts: dict[int, list[GroupReviewLog]] = defaultdict(list)
    logs = session.scalars(
        select(GroupReviewLog)
        .where(GroupReviewLog.session_id == session_id)
        .order_by(GroupReviewLog.created_at, GroupReviewLog.id)
    )
    for log in logs:
        attempts[log.word_id].append(log)

    results: list[GroupFinishResult] = []
    for word_id, word_attempts in attempts.items():
        answered = {log.exercise for log in word_attempts if log.correct}
        if not set(EXERCISE_ROUNDS) <= answered:
            continue
        label_id = word_attempts[-1].label_id
        # Метку удалили вместе с её кругами — отмечать негде
        if label_id is None:
            continue

        rows = list(
            session.scalars(
                select(GroupCycleWord)
                .where(GroupCycleWord.label_id == label_id, GroupCycleWord.word_id == word_id)
                .order_by(GroupCycleWord.cycle)
            )
        )
        already = any(row.done_session_id == session_id for row in rows)
        if not already:
            undone = next((row for row in rows if row.done_at is None), None)
            if undone is None:
                continue
            undone.done_at = now
            undone.done_session_id = session_id

        results.append(
            GroupFinishResult(
                word_id=word_id,
                mistakes=sum(1 for log in word_attempts if not log.correct),
            )
        )

    session.flush()
    return results


def restart_group(session: Session, label: Label, rng: random.Random | None = None) -> None:
    """«Начать круг заново»: новый круг в новом порядке, прежние круги — прочь.
    Прогресс слов и журнал не трогаются (FR-018)."""
    rng = rng or random.Random()
    plan = plan_restart(members(session, label.id), _entries(session, label.id), rng)
    _apply(session, label.id, plan)
