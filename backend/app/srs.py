"""Интервальные повторения: раунды упражнений + SM-2.

Модуль намеренно не знает про SQLAlchemy и не ходит в базу — все функции чистые,
время и генератор случайных чисел передаются параметрами. Это позволяет
тестировать расписание таблично, без подмены системного времени.
"""

from __future__ import annotations

import random
from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from app.config import settings
from app.models import ExerciseType, WordStatus

# Сколько успешных занятий проходит слово, откатившееся в изучение после
# забывания, прежде чем снова выпуститься в повторения. Тип упражнения из шага
# не выводится — его задают раунды занятия, поэтому здесь число, а не кортеж.
RELEARN_STEPS: int = 4

# Шаг, на который откатывается слово, забытое на повторении.
# Не 0: слову, которое когда-то уже было выпущено, начинать с нуля незачем.
RELEARN_STEP = 1

# Раунды занятия: по раунду на тип упражнения, порядок фиксирован и растёт по
# сложности — узнавание, обратный перевод, сборка, воспроизведение на слух.
# Порядок один на оба режима: и знакомство с новым словом, и повторение
# изученного идут одними и теми же четырьмя раундами. Карточка-знакомство
# в раундах не участвует: на ней слово уже показали.
EXERCISE_ROUNDS: tuple[ExerciseType, ...] = (
    ExerciseType.CHOICE_RU_EN,
    ExerciseType.CHOICE_EN_RU,
    ExerciseType.LETTERS,
    ExerciseType.DICTATION,
)

FIRST_INTERVAL_DAYS = 1.0
SECOND_INTERVAL_DAYS = 3.0
LAPSE_EASE_PENALTY = 0.20
JITTER_RANGE = (0.9, 1.1)


@dataclass(frozen=True, slots=True)
class SrsState:
    """Снимок прогресса по слову. Иммутабельный: переходы возвращают новый снимок."""

    status: WordStatus = WordStatus.LEARNING
    step: int = 0
    repetitions: int = 0
    ease: float = settings.initial_ease
    interval_days: float = 0.0
    lapses: int = 0
    due_at: datetime | None = None


def derive_quality(*, correct: bool, used_hint: bool, attempt: int) -> int:
    """Оценка ответа по шкале SM-2 (0..5), выведенная из поведения пользователя.

    Спрашивать «насколько легко было?» как в Anki мы не хотим — оценку
    восстанавливаем сами: подсказка и вторая попытка снижают качество.
    """
    if not correct:
        return 2
    if attempt >= 2:
        return 3
    if used_hint:
        return 4
    return 5


def update_ease(ease: float, quality: int) -> float:
    """Классическая формула SM-2 для ease factor с нижней отсечкой."""
    delta = 0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)
    return max(settings.min_ease, ease + delta)


def _jitter(rng: random.Random | None) -> float:
    """Разброс срока повторения, чтобы слова одной сессии не всплывали одним днём."""
    if rng is None:
        return 1.0
    return rng.uniform(*JITTER_RANGE)


def start_learning(now: datetime) -> SrsState:
    """Слово взято в изучение: встаёт на первый шаг и доступно сразу."""
    return SrsState(
        status=WordStatus.LEARNING,
        step=0,
        ease=settings.initial_ease,
        due_at=now,
    )


def mark_known(now: datetime) -> SrsState:
    """«Уже знаю»: слово выводится из оборота и больше не предлагается."""
    return SrsState(status=WordStatus.KNOWN, step=RELEARN_STEPS, due_at=now)


def force_status(
    state: SrsState,
    status: WordStatus,
    now: datetime,
    rng: random.Random | None = None,
) -> SrsState:
    """Статус, выставленный вручную из словаря.

    Это не ответ на упражнение: ease и lapses остаются прежними, меняется
    только то, без чего новый статус не имеет смысла. Расписание слова,
    выведенного из оборота, замирает — возврат в review поднимет прежний срок.
    """
    if status in (WordStatus.KNOWN, WordStatus.SUSPENDED):
        return replace(state, status=status)

    if status == WordStatus.LEARNING:
        return replace(
            state,
            status=status,
            step=0,
            repetitions=0,
            interval_days=0.0,
            due_at=now,
        )

    if state.interval_days > 0:
        # Слово уже выпускалось: накопленное расписание важнее нового
        return replace(state, status=WordStatus.REVIEW, due_at=state.due_at or now)
    return graduate(state, now=now, rng=rng)


@dataclass(frozen=True, slots=True)
class AttemptOutcome:
    """Одна попытка ответа: всё, из чего выводится её оценка."""

    correct: bool
    used_hint: bool
    attempt: int


def session_quality(outcomes: Iterable[AttemptOutcome]) -> int:
    """Итоговая оценка слова за занятие-повторение — худшая из попыток.

    Слово проходит четыре раунда, но расписание двигается один раз, поэтому
    оценка нужна одна. Берём минимум: одна ошибка за занятие означает, что
    слово забыто, сколько бы верных ответов ни было рядом.

    Пустой ввод — ошибка вызывающего: у слова без единой попытки нечего
    оценивать, и расписание ему не пересчитывают.
    """
    return min(
        derive_quality(
            correct=outcome.correct, used_hint=outcome.used_hint, attempt=outcome.attempt
        )
        for outcome in outcomes
    )


def apply_answer(
    state: SrsState,
    *,
    quality: int,
    now: datetime,
    rng: random.Random | None = None,
) -> SrsState:
    """Пересчитать прогресс после ответа.

    В режиме learning двигаемся по шагам, в режиме review — по SM-2.
    """
    if state.status in (WordStatus.KNOWN, WordStatus.SUSPENDED):
        return state
    if state.status == WordStatus.LEARNING:
        return _apply_learning(state, quality=quality, now=now, rng=rng)
    return _apply_review(state, quality=quality, now=now, rng=rng)


def _apply_learning(
    state: SrsState, *, quality: int, now: datetime, rng: random.Random | None
) -> SrsState:
    if quality < 3:
        # Откат ровно на шаг назад, а не в начало: полный сброс демотивирует.
        return replace(state, step=max(0, state.step - 1), due_at=now)

    next_step = state.step + 1
    if next_step < RELEARN_STEPS:
        return replace(state, step=next_step, due_at=now)
    return graduate(state, now=now, rng=rng)


def graduate(state: SrsState, *, now: datetime, rng: random.Random | None = None) -> SrsState:
    """Слово прошло занятие и переходит в режим повторений.

    Публичная: занятие-изучение выпускает слово этим переходом напрямую, по
    итогу четырёх раундов, а не через `apply_answer` — ошибка внутри занятия
    расписание не наказывает, поэтому `ease` и `lapses` здесь не трогаются.
    """
    interval = FIRST_INTERVAL_DAYS
    return replace(
        state,
        status=WordStatus.REVIEW,
        step=RELEARN_STEPS,
        repetitions=1,
        interval_days=interval,
        due_at=now + timedelta(days=interval * _jitter(rng)),
    )


def _apply_review(
    state: SrsState, *, quality: int, now: datetime, rng: random.Random | None
) -> SrsState:
    if quality < 3:
        # Слово забыто: вернуть в learning и показать ещё раз в этой же сессии.
        return replace(
            state,
            status=WordStatus.LEARNING,
            step=RELEARN_STEP,
            repetitions=0,
            ease=max(settings.min_ease, state.ease - LAPSE_EASE_PENALTY),
            interval_days=0.0,
            lapses=state.lapses + 1,
            due_at=now,
        )

    ease = update_ease(state.ease, quality)
    repetitions = state.repetitions + 1
    if repetitions == 1:
        interval = FIRST_INTERVAL_DAYS
    elif repetitions == 2:
        interval = SECOND_INTERVAL_DAYS
    else:
        interval = state.interval_days * ease
    interval = min(interval, settings.max_interval_days)

    return replace(
        state,
        status=WordStatus.REVIEW,
        repetitions=repetitions,
        ease=ease,
        interval_days=interval,
        due_at=now + timedelta(days=interval * _jitter(rng)),
    )
