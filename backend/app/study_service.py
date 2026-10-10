"""Учебная сессия: связывает чистый SRS, генератор упражнений и базу."""

from __future__ import annotations

import random
import uuid
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.exercises import build_exercise, check_answer, correct_answer_for, order_round
from app.models import ExerciseType, Progress, ReviewLog, Setting, Word, WordStatus
from app.schemas import (
    AnswerRequest,
    AnswerResponse,
    ExerciseRound,
    NewWordsOrder,
    ProgressOut,
    SelectResponse,
    SessionCounts,
    SessionFinishResult,
    SessionMode,
    SessionOut,
    WordOut,
)
from app.srs import (
    EXERCISE_ROUNDS,
    EXERCISES_WITHOUT_HINT,
    AttemptOutcome,
    SrsState,
    apply_answer,
    derive_quality,
    force_status,
    graduate,
    mark_known,
    session_quality,
    start_learning,
)

ACTIVE_STATUSES = (WordStatus.LEARNING.value, WordStatus.REVIEW.value)

# Ключ порядка новых слов в таблице `settings`
NEW_WORDS_ORDER_KEY = "new_words_order"


class WordNotInStudyError(Exception):
    """Слово ещё не взято в изучение — отвечать на упражнение по нему нельзя."""


class WordNotNewError(Exception):
    """Поднять в очереди можно только новое слово — у этого уже есть прогресс."""


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


def new_words_query(
    limit: int,
    exclude_ids: Sequence[int] = (),
    order: NewWordsOrder = NewWordsOrder.OLDEST_FIRST,
):
    """Слова, которых ещё нет в изучении: сначала поднятые, затем остальные,
    внутри каждой группы — в выбранном порядке добавления.

    Порядок добавления — это `id`, а не `created_at`: импорт ставит всем строкам
    файла один и тот же момент, а `id` растёт в порядке вставки, то есть
    в порядке строк файла.
    """
    by_id = Word.id.desc() if order is NewWordsOrder.NEWEST_FIRST else Word.id.asc()
    stmt = (
        select(Word)
        .outerjoin(Progress, Progress.word_id == Word.id)
        .where(Progress.word_id.is_(None))
        .order_by(Word.priority.desc(), by_id)
    )
    if exclude_ids:
        stmt = stmt.where(Word.id.notin_(exclude_ids))
    return stmt.limit(limit)


def get_new_words_order(session: Session) -> NewWordsOrder:
    """Порядок новых слов из таблицы `settings`.

    Строки нет — действует порядок добавления, как до появления настройки.
    Неизвестное значение (база правлена руками) читается так же: из-за него
    не должен ломаться отбор слов.
    """
    setting = session.get(Setting, NEW_WORDS_ORDER_KEY)
    if setting is None:
        return NewWordsOrder.OLDEST_FIRST
    try:
        return NewWordsOrder(setting.value)
    except ValueError:
        return NewWordsOrder.OLDEST_FIRST


def set_new_words_order(session: Session, order: NewWordsOrder) -> None:
    setting = session.get(Setting, NEW_WORDS_ORDER_KEY)
    if setting is None:
        session.add(Setting(key=NEW_WORDS_ORDER_KEY, value=order.value))
    else:
        setting.value = order.value
    session.flush()


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


def fetch_new_words(
    session: Session, now: datetime, limit: int, exclude_ids: Sequence[int] = ()
) -> list[Word]:
    allowance = new_words_allowance(session, now, limit)
    if allowance == 0:
        return []
    # Настройку читаем при каждом отборе, а не держим в памяти: сервер stateless,
    # и смена порядка действует с ближайшего отбора — занятия и замены
    order = get_new_words_order(session)
    return list(session.scalars(new_words_query(allowance, exclude_ids, order)))


def _due_words(session: Session, now: datetime, limit: int) -> list[Word]:
    """Слова в обороте, у которых подошёл срок: самые просроченные первыми.

    Learning и review берутся одним запросом — на повторении важен срок,
    а не то, на каком этапе слово находится.
    """
    stmt = (
        select(Word)
        .join(Progress, Progress.word_id == Word.id)
        .where(Progress.status.in_(ACTIVE_STATUSES), Progress.due_at <= now)
        .order_by(Progress.due_at)
        .limit(limit)
    )
    return list(session.scalars(stmt))


# ------------------------------------------------------------------------ сессия


def build_session(
    session: Session,
    now: datetime,
    mode: SessionMode,
    rng: random.Random | None = None,
) -> SessionOut:
    """Собрать стартовый набор занятия — 5 слов выбранной категории.

    `learn` даёт новые слова на знакомство, `review` — очередь упражнений по
    словам, у которых подошёл срок. Очередь дальше живёт на фронте: бэкенд
    остаётся stateless, поэтому перезагрузка страницы просто пересобирает
    занятие из актуального прогресса.
    """
    rng = rng or random.Random()

    new_words: list[Word] = []
    due: list[Word] = []
    rounds: list[ExerciseRound] = []
    session_id: str | None = None

    if mode is SessionMode.LEARN:
        new_words = fetch_new_words(session, now, settings.new_words_per_session)
        # План раундов изучения приходит отдельным запросом: его состав
        # известен только после знакомства, где «Уже знаю» меняет слова
        words = new_words
    else:
        due = _due_words(session, now, settings.review_words_per_session)
        rounds = _rounds_for(session, due, rng)
        words = due

    if words:
        # Ключ занятия нужен там, где есть чем заняться: по нему `finish`
        # соберёт попытки занятия и выведет итог по каждому слову.
        session_id = str(uuid.uuid4())

    learning = sum(1 for w in due if w.progress.status == WordStatus.LEARNING.value)

    in_study = (
        session.scalar(
            select(func.count(Progress.word_id)).where(Progress.status.in_(ACTIVE_STATUSES))
        )
        or 0
    )

    return SessionOut(
        mode=mode,
        session_id=session_id,
        new_words=[WordOut.model_validate(w) for w in new_words],
        rounds=rounds,
        counts=SessionCounts(
            new=len(new_words),
            learning=learning,
            review_due=len(due) - learning,
            in_study=in_study,
        ),
    )


def _rounds_for(
    session: Session, words: Sequence[Word], rng: random.Random
) -> list[ExerciseRound]:
    """Раунды по типам упражнений: в каждом — по карточке на каждое слово.

    Порядок слов у каждого раунда свой и не повторяет предыдущий, иначе слова
    запоминаются по месту в очереди; при трёх словах и больше раунд
    не начинается со слова, которым кончился предыдущий. План общий для повторения
    и `/study/rounds`, так что правило действует в обоих режимах.
    """
    if not words:
        return []
    rounds: list[ExerciseRound] = []
    previous: list[Word] | None = None
    for exercise_type in EXERCISE_ROUNDS:
        last = previous[-1] if previous else None
        ordered = order_round(words, previous, last, rng, key=lambda w: w.id)
        rounds.append(
            ExerciseRound(
                exercise=exercise_type,
                exercises=[
                    build_exercise(
                        session,
                        word,
                        exercise_type,
                        # Банк букв даём и на повторении: подсказка внизу карточки
                        # обещает выбор мышью, а кто хочет сложнее — жмёт «Скрыть буквы»
                        show_letters=True,
                        rng=rng,
                    )
                    for word in ordered
                ],
            )
        )
        previous = ordered
    return rounds


def build_rounds(
    session: Session,
    word_ids: Sequence[int],
    rng: random.Random | None = None,
) -> list[ExerciseRound]:
    """План раундов по готовому списку слов — по тем, что взяты в изучение.

    Занятие-изучение узнаёт свой состав только к концу знакомства: «Уже знаю»
    выводит слово из оборота и добирает замену. Поэтому раунды изучения едут
    отдельным запросом, а не вместе с занятием. Состояния он не создаёт —
    принимает слова, возвращает карточки.
    """
    rng = rng or random.Random()

    words: list[Word] = []
    for word_id in word_ids:
        word = session.get(Word, word_id)
        # Слово могли удалить или вывести из оборота между знакомством
        # и запросом: занятие идёт дальше на остальных словах
        if word is None or word.progress is None:
            continue
        if word.progress.status not in ACTIVE_STATUSES:
            continue
        words.append(word)

    return _rounds_for(session, words, rng)


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
    session_id: str | None = None,
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
            session_id=session_id,
        )
    )


def select_word(
    session: Session,
    word: Word,
    action: str,
    now: datetime,
    exclude_ids: Sequence[int] = (),
) -> SelectResponse:
    """Обработать экран знакомства: «Уже знаю» или «Изучить»."""
    progress = word.progress

    if progress is None:
        # Заполняем состояние явно, не полагаясь на defaults колонок: они
        # применяются только при INSERT, а состояние нужно уже сейчас.
        before = start_learning(now)
        progress = Progress(word_id=word.id, started_at=now, updated_at=now)
        write_state(progress, before, now)
        session.add(progress)
        word.progress = progress
        # Отметка «Учить первым» живёт, пока слово новое
        word.priority = False
    else:
        before = state_from_progress(progress)

    if action == "know":
        state = mark_known(now)
    else:
        # «Изучить» только заводит прогресс: упражнения слова придут раундами,
        # а расписание внутри занятия не двигается — его пересчитает `finish`
        state = start_learning(now)

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

    # «Уже знаю» выводит слово из оборота — добираем взамен следующее новое,
    # чтобы в занятии осталось столько же слов на изучение, сколько было.
    # Запрос идёт после flush: помеченное слово уже отсеется по своему прогрессу.
    replacement = None
    if action == "know":
        replacement = next(iter(fetch_new_words(session, now, 1, exclude_ids)), None)

    return SelectResponse(
        progress=ProgressOut.model_validate(progress),
        replacement=WordOut.model_validate(replacement) if replacement else None,
    )


def answer_exercise(
    session: Session,
    word: Word,
    request: AnswerRequest,
    now: datetime,
    rng: random.Random | None = None,
) -> AnswerResponse:
    """Проверить ответ, записать попытку и решить, вернётся ли карточка.

    Режимы здесь не расходятся: оба только пишут попытку в журнал. Расписание
    внутри занятия неподвижно — слово получает по упражнению в каждом из
    раундов, и одно обновление на все раунды ставит `finish`.
    """
    rng = rng or random.Random()
    if word.progress is None:
        raise WordNotInStudyError

    before = state_from_progress(word.progress)
    correct = check_answer(word, request.exercise, request.answer)
    used_hint = request.used_hint and request.exercise not in EXERCISES_WITHOUT_HINT
    quality = derive_quality(correct=correct, used_hint=used_hint, attempt=request.attempt)

    repeat = not correct
    # Повтор после ошибки — тот же тип, но карточка собирается заново:
    # запомненная позиция кнопки не должна подменять знание слова
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

    _log(
        session,
        word_id=word.id,
        exercise=request.exercise,
        correct=correct,
        answer=request.answer,
        used_hint=used_hint,
        attempt=request.attempt,
        quality=quality,
        duration_ms=request.duration_ms,
        before=before,
        # Статус до и после совпадает: расписание внутри занятия не трогаем
        after=before,
        now=now,
        session_id=request.session_id,
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
        repeat_in_session=repeat,
        next_exercise=next_exercise,
        progress=ProgressOut.model_validate(word.progress),
    )


def finish_session(
    session: Session,
    session_id: str,
    mode: SessionMode,
    now: datetime,
    rng: random.Random | None = None,
) -> list[SessionFinishResult]:
    """Подвести итог занятия и один раз пересчитать расписание слов.

    Оценку выводит сервер, а не клиент: попытки занятия лежат в `review_log`
    под своим `session_id`, и по ним видно и то, прошло ли слово все
    раунды, и была ли по нему ошибка.

    Режимы расходятся ровно в одном — как из состояния слова получается новое.
    Повторение считает итог по худшей попытке: ошибка означает, что слово
    забыто. Изучение выпускает слово независимо от ошибок: слово изучается
    впервые, забыть его было нельзя, а ошибка уже закрыта верным ответом
    в том же раунде.
    """
    rng = rng or random.Random()

    attempts: dict[int, list[ReviewLog]] = defaultdict(list)
    logs = session.scalars(
        select(ReviewLog)
        .where(ReviewLog.session_id == session_id)
        .order_by(ReviewLog.created_at)
    )
    for log in logs:
        attempts[log.word_id].append(log)

    results: list[SessionFinishResult] = []
    for word_id, word_attempts in attempts.items():
        answered = {log.exercise for log in word_attempts if log.correct}
        # FR-016: слово, не дошедшее до конца раундов, не трогаем вовсе
        if not set(EXERCISE_ROUNDS) <= answered:
            continue

        word = session.get(Word, word_id)
        # FR-020: слово могли вывести из оборота или удалить прямо во время занятия
        if word is None or word.progress is None:
            continue
        if word.progress.status not in ACTIVE_STATUSES:
            continue
        # Идемпотентность: расписание уже пересчитано после последней попытки
        if word.progress.updated_at >= max(log.created_at for log in word_attempts):
            continue

        quality = session_quality(
            AttemptOutcome(
                correct=log.correct, used_hint=log.used_hint, attempt=log.attempt
            )
            for log in word_attempts
        )
        before = state_from_progress(word.progress)
        after = (
            graduate(before, now=now, rng=rng)
            if mode is SessionMode.LEARN
            else apply_answer(before, quality=quality, now=now, rng=rng)
        )
        write_state(word.progress, after, now)

        results.append(
            SessionFinishResult(
                word_id=word_id,
                mistakes=sum(1 for log in word_attempts if not log.correct),
                quality=quality,
                progress=ProgressOut.model_validate(word.progress),
            )
        )

    session.flush()
    return results


def reset_word(session: Session, word: Word, now: datetime) -> None:
    """Сбросить прогресс: слово снова станет новым."""
    if word.progress is not None:
        session.delete(word.progress)
        word.progress = None
        session.flush()


def set_word_status(
    session: Session,
    word: Word,
    status: WordStatus | Literal["new"],
    now: datetime,
    rng: random.Random | None = None,
) -> Progress | None:
    """Сменить статус слова вручную — из словаря, а не по ходу занятия.

    `new` — не статус, а его отсутствие: строка прогресса удаляется и слово
    снова становится новым. Ответом такая правка не считается, поэтому
    в `review_log` ничего не пишем.
    """
    if status == "new":
        reset_word(session, word, now)
        return None

    progress = word.progress
    if progress is None:
        # Слово ещё не в изучении: заводим строку прогресса, как при «Изучить»
        progress = Progress(word_id=word.id, started_at=now, updated_at=now)
        write_state(progress, start_learning(now), now)
        session.add(progress)
        word.progress = progress
        # Отметка «Учить первым» живёт, пока слово новое
        word.priority = False

    state = force_status(state_from_progress(progress), WordStatus(status), now, rng)
    write_state(progress, state, now)
    session.flush()
    return progress


def set_word_priority(session: Session, word: Word, priority: bool) -> None:
    """Поставить или снять отметку «Учить первым».

    Снять можно всегда — у слова с прогрессом отметки и так нет, и запрос
    остаётся идемпотентным. Поставить — только новому слову: иначе отметка
    висела бы на слове, которое «Изучение» уже не возьмёт.
    """
    if priority and word.progress is not None:
        raise WordNotNewError
    word.priority = priority
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
