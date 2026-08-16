"""Интервальные повторения: learning steps + SM-2.

Модуль намеренно не знает про SQLAlchemy и не ходит в базу — все функции чистые,
время и генератор случайных чисел передаются параметрами. Это позволяет
тестировать расписание таблично, без подмены системного времени.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from app.config import settings
from app.models import ExerciseType, WordStatus

# Шаги первого знакомства со словом. Проходятся внутри одной сессии,
# сложность растёт: узнавание -> выбор -> сборка -> воспроизведение на слух.
LEARNING_STEPS: tuple[ExerciseType, ...] = (
    ExerciseType.INTRO,
    ExerciseType.CHOICE_RU_EN,
    ExerciseType.LETTERS,
    ExerciseType.DICTATION,
)

# Шаг, на который откатывается слово, забытое на повторении.
# Не 0: показывать карточку-знакомство знакомому слову бессмысленно.
RELEARN_STEP = 1

# Упражнения для режима повторения (без карточки-знакомства).
REVIEW_EXERCISES: tuple[ExerciseType, ...] = (
    ExerciseType.CHOICE_EN_RU,
    ExerciseType.LETTERS,
    ExerciseType.DICTATION,
)

# Веса выбора упражнения на повторении: чем дольше слово живёт, тем чаще
# попадаются сложные форматы.
_REVIEW_WEIGHTS: tuple[tuple[int, tuple[int, int, int]], ...] = (
    (2, (3, 2, 1)),
    (5, (2, 3, 2)),
)
_REVIEW_WEIGHTS_LATE = (1, 3, 3)

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
    return SrsState(status=WordStatus.KNOWN, step=len(LEARNING_STEPS), due_at=now)


def exercise_for(state: SrsState, rng: random.Random | None = None) -> ExerciseType:
    """Какое упражнение показать для текущего состояния слова."""
    if state.status == WordStatus.LEARNING:
        return LEARNING_STEPS[min(state.step, len(LEARNING_STEPS) - 1)]
    return pick_review_exercise(state.repetitions, rng)


def pick_review_exercise(repetitions: int, rng: random.Random | None = None) -> ExerciseType:
    weights = _REVIEW_WEIGHTS_LATE
    for threshold, candidate in _REVIEW_WEIGHTS:
        if repetitions <= threshold:
            weights = candidate
            break
    if rng is None:
        return REVIEW_EXERCISES[weights.index(max(weights))]
    return rng.choices(REVIEW_EXERCISES, weights=weights, k=1)[0]


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
    if next_step < len(LEARNING_STEPS):
        return replace(state, step=next_step, due_at=now)
    return _graduate(state, now=now, rng=rng)


def _graduate(state: SrsState, *, now: datetime, rng: random.Random | None) -> SrsState:
    """Все шаги пройдены — слово переходит в режим повторений."""
    interval = FIRST_INTERVAL_DAYS
    return replace(
        state,
        status=WordStatus.REVIEW,
        step=len(LEARNING_STEPS),
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
