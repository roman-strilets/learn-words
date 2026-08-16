"""Учебная сессия: связывает чистый SRS, генератор упражнений и базу."""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.exercises import build_exercise, check_answer, correct_answer_for
from app.models import ExerciseType, Progress, ReviewLog, Word, WordStatus
from app.schemas import (
    AnswerRequest,
    AnswerResponse,
    Exercise,
    ProgressOut,
    SelectResponse,
    SessionCounts,
    SessionOut,
    WordOut,
)
from app.srs import SrsState, apply_answer, derive_quality, exercise_for, mark_known, start_learning

ACTIVE_STATUSES = (WordStatus.LEARNING.value, WordStatus.REVIEW.value)


class WordNotInStudyError(Exception):
    """Слово ещё не взято в изучение — отвечать на упражнение по нему нельзя."""


# ------------------------------------------------------- перекладывание состояния


def state_from_progress(progress: Progress) -> SrsState:
    return SrsState(
        status=WordStatus(progress.status),
        step=progress.step,
        repetitions=progress.repetitions,
        ease=progress.ease,
        interval_days=progress.interval_days,
        lapses=progress.lapses,
        due_at=progress.due_at,
    )


def write_state(progress: Progress, state: SrsState, now: datetime) -> None:
    progress.status = state.status.value
    progress.step = state.step
    progress.repetitions = state.repetitions
    progress.ease = state.ease
    progress.interval_days = state.interval_days
    progress.lapses = state.lapses
    progress.due_at = state.due_at or now
    progress.updated_at = now


# ------------------------------------------------------------------------ запросы


def new_words_query(limit: int):
    """Слова, которых ещё нет в изучении, в порядке появления в словаре."""
    return (
        select(Word)
        .outerjoin(Progress, Progress.word_id == Word.id)
        .where(Progress.word_id.is_(None))
        .order_by(Word.id)
        .limit(limit)
    )


def _started_today(session: Session, now: datetime) -> int:
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    stmt = select(func.count(Progress.word_id)).where(
        Progress.started_at >= day_start,
        Progress.status.in_(ACTIVE_STATUSES),
    )
    return session.scalar(stmt) or 0


def new_words_allowance(session: Session, now: datetime, requested: int) -> int:
    """Сколько новых слов можно предложить с учётом дневного лимита."""
    remaining = settings.daily_new_limit - _started_today(session, now)
    return max(0, min(requested, remaining))


def fetch_new_words(session: Session, now: datetime, limit: int) -> list[Word]:
    allowance = new_words_allowance(session, now, limit)
    if allowance == 0:
        return []
    return list(session.scalars(new_words_query(allowance)))


def _due_words(session: Session, now: datetime, status: WordStatus, limit: int) -> list[Word]:
    stmt = (
        select(Word)
        .join(Progress, Progress.word_id == Word.id)
        .where(Progress.status == status.value, Progress.due_at <= now)
        .order_by(Progress.due_at)
        .limit(limit)
    )
    return list(session.scalars(stmt))


# ------------------------------------------------------------------------ сессия


def build_session(session: Session, now: datetime, rng: random.Random | None = None) -> SessionOut:
    """Собрать стартовый набор сессии.

    Очередь дальше живёт на фронте: бэкенд остаётся stateless, поэтому
    перезагрузка страницы просто пересобирает сессию из актуального прогресса.
    """
    rng = rng or random.Random()

    reviews = _due_words(session, now, WordStatus.REVIEW, settings.session_size)
    learning = _due_words(session, now, WordStatus.LEARNING, settings.session_size)

    queue: list[Exercise] = []
    for word in reviews + learning:
        state = state_from_progress(word.progress)
        exercise_type = exercise_for(state, rng)
        queue.append(
            build_exercise(
                session,
                word,
                exercise_type,
                show_letters=state.status == WordStatus.LEARNING,
                rng=rng,
            )
        )
    rng.shuffle(queue)

    new_words = fetch_new_words(session, now, settings.new_words_per_session)

    in_study = (
        session.scalar(
            select(func.count(Progress.word_id)).where(Progress.status.in_(ACTIVE_STATUSES))
        )
        or 0
    )

    return SessionOut(
        new_words=[WordOut.model_validate(w) for w in new_words],
        exercises=queue,
        counts=SessionCounts(
            new=len(new_words),
            learning=len(learning),
            review_due=len(reviews),
            in_study=in_study,
        ),
    )


def _log(
    session: Session,
    *,
    word_id: int,
    exercise: ExerciseType,
    correct: bool,
    answer: str | None,
    used_hint: bool,
    attempt: int,
    quality: int,
    duration_ms: int | None,
    before: SrsState,
    after: SrsState,
    now: datetime,
) -> None:
    session.add(
        ReviewLog(
            word_id=word_id,
            exercise=exercise.value,
            correct=correct,
            answer=answer,
            used_hint=used_hint,
            attempt=attempt,
            quality=quality,
            duration_ms=duration_ms,
            status_before=before.status.value,
            status_after=after.status.value,
            ease_after=after.ease,
            interval_after=after.interval_days,
            created_at=now,
        )
    )


def _next_exercise(
    session: Session, word: Word, state: SrsState, now: datetime, rng: random.Random
) -> Exercise | None:
    """Упражнение для повторного показа в этой же сессии, если слово ещё не готово."""
    if state.status != WordStatus.LEARNING:
        return None
    if state.due_at is not None and state.due_at > now:
        return None
    return build_exercise(session, word, exercise_for(state, rng), show_letters=True, rng=rng)


def select_word(
    session: Session, word: Word, action: str, now: datetime, rng: random.Random | None = None
) -> SelectResponse:
    """Обработать экран знакомства: «Уже знаю» или «Изучить»."""
    rng = rng or random.Random()
    progress = word.progress

    if progress is None:
        # Заполняем состояние явно, не полагаясь на defaults колонок: они
        # применяются только при INSERT, а состояние нужно уже сейчас.
        before = start_learning(now)
        progress = Progress(word_id=word.id, started_at=now, updated_at=now)
        write_state(progress, before, now)
        session.add(progress)
        word.progress = progress
    else:
        before = state_from_progress(progress)

    if action == "know":
        state = mark_known(now)
    else:
        # Нажатие «Изучить» — это и есть успешное прохождение карточки-знакомства.
        state = apply_answer(start_learning(now), quality=5, now=now, rng=rng)

    write_state(progress, state, now)
    _log(
        session,
        word_id=word.id,
        exercise=ExerciseType.INTRO,
        correct=True,
        answer=action,
        used_hint=False,
        attempt=1,
        quality=5,
        duration_ms=None,
        before=before,
        after=state,
        now=now,
    )
    session.flush()

    return SelectResponse(
        progress=ProgressOut.model_validate(progress),
        next_exercise=_next_exercise(session, word, state, now, rng),
    )


def answer_exercise(
    session: Session,
    word: Word,
    request: AnswerRequest,
    now: datetime,
    rng: random.Random | None = None,
) -> AnswerResponse:
    rng = rng or random.Random()
    if word.progress is None:
        raise WordNotInStudyError

    before = state_from_progress(word.progress)
    correct = check_answer(word, request.exercise, request.answer)
    quality = derive_quality(correct=correct, used_hint=request.used_hint, attempt=request.attempt)
    after = apply_answer(before, quality=quality, now=now, rng=rng)

    write_state(word.progress, after, now)
    _log(
        session,
        word_id=word.id,
        exercise=request.exercise,
        correct=correct,
        answer=request.answer,
        used_hint=request.used_hint,
        attempt=request.attempt,
        quality=quality,
        duration_ms=request.duration_ms,
        before=before,
        after=after,
        now=now,
    )
    session.flush()

    return AnswerResponse(
        correct=correct,
        correct_answer=correct_answer_for(word, request.exercise),
        word=word.word,
        translation=word.translation,
        example=word.example,
        example_translation=word.example_translation,
        quality=quality,
        repeat_in_session=after.status == WordStatus.LEARNING,
        next_exercise=_next_exercise(session, word, after, now, rng),
        progress=ProgressOut.model_validate(word.progress),
    )


def reset_word(session: Session, word: Word, now: datetime) -> None:
    """Сбросить прогресс: слово снова станет новым."""
    if word.progress is not None:
        session.delete(word.progress)
        word.progress = None
        session.flush()


def due_counts(session: Session, now: datetime) -> tuple[int, int]:
    """Сколько слов готово к повторению сейчас и до конца суток."""
    end_of_day = now.replace(hour=23, minute=59, second=59, microsecond=999_999)
    base = select(func.count(Progress.word_id)).where(Progress.status.in_(ACTIVE_STATUSES))
    now_count = session.scalar(base.where(Progress.due_at <= now)) or 0
    today_count = session.scalar(base.where(Progress.due_at <= end_of_day)) or 0
    return now_count, today_count


def day_bounds(now: datetime) -> tuple[datetime, datetime]:
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)
