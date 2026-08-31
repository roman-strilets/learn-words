"""Расписание повторений: выпуск слова и SM-2."""

import random
from datetime import datetime, timedelta

import pytest

from app.config import settings
from app.models import ExerciseType, WordStatus
from app.srs import (
    EXERCISE_ROUNDS,
    FIRST_INTERVAL_DAYS,
    RELEARN_STEP,
    RELEARN_STEPS,
    AttemptOutcome,
    SrsState,
    apply_answer,
    derive_quality,
    force_status,
    graduate,
    mark_known,
    session_quality,
    start_learning,
    update_ease,
)

NOW = datetime(2026, 1, 1, 12, 0, 0)
# rng=None убирает джиттер, поэтому интервалы в тестах точные
NO_JITTER = None


@pytest.mark.parametrize(
    ("correct", "used_hint", "attempt", "expected"),
    [
        (True, False, 1, 5),
        (True, True, 1, 4),
        (True, False, 2, 3),
        (True, True, 3, 3),
        (False, False, 1, 2),
        (False, True, 4, 2),
    ],
)
def test_derive_quality(correct, used_hint, attempt, expected):
    assert derive_quality(correct=correct, used_hint=used_hint, attempt=attempt) == expected


def test_a_word_graduates_after_the_relearn_steps():
    # Шаг больше не выбирает упражнение, но по-прежнему считает занятия:
    # столько их проходит слово, откатившееся в изучение после забывания
    state = start_learning(NOW)
    for _ in range(RELEARN_STEPS):
        assert state.status is WordStatus.LEARNING
        state = apply_answer(state, quality=5, now=NOW, rng=NO_JITTER)

    assert state.status is WordStatus.REVIEW


def test_wrong_answer_steps_back_one_not_to_zero():
    state = SrsState(status=WordStatus.LEARNING, step=3, due_at=NOW)
    state = apply_answer(state, quality=2, now=NOW, rng=NO_JITTER)

    assert state.status is WordStatus.LEARNING
    assert state.step == 2
    assert state.due_at == NOW  # показать ещё раз в этой же сессии


def test_wrong_answer_on_first_step_stays_at_zero():
    state = start_learning(NOW)
    assert apply_answer(state, quality=2, now=NOW, rng=NO_JITTER).step == 0


def test_graduation_schedules_tomorrow():
    state = SrsState(status=WordStatus.LEARNING, step=RELEARN_STEPS - 1, due_at=NOW)
    state = apply_answer(state, quality=5, now=NOW, rng=NO_JITTER)

    assert state.status is WordStatus.REVIEW
    assert state.repetitions == 1
    assert state.interval_days == 1.0
    assert state.due_at == NOW + timedelta(days=1)


def test_review_intervals_grow():
    state = start_learning(NOW)
    for _ in range(RELEARN_STEPS):
        state = apply_answer(state, quality=5, now=NOW, rng=NO_JITTER)

    intervals = [state.interval_days]
    for _ in range(3):
        state = apply_answer(state, quality=5, now=NOW, rng=NO_JITTER)
        intervals.append(round(state.interval_days, 2))

    assert intervals == [1.0, 3.0, 8.1, 22.68]
    assert intervals == sorted(intervals)


def test_lapse_returns_to_learning_and_counts():
    state = SrsState(
        status=WordStatus.REVIEW, step=4, repetitions=5, ease=2.5, interval_days=40.0, due_at=NOW
    )
    state = apply_answer(state, quality=2, now=NOW, rng=NO_JITTER)

    assert state.status is WordStatus.LEARNING
    assert state.step == RELEARN_STEP
    assert state.repetitions == 0
    assert state.lapses == 1
    assert state.interval_days == 0.0
    assert state.ease == pytest.approx(2.3)
    assert state.due_at == NOW


def test_ease_never_drops_below_floor():
    ease = settings.initial_ease
    for _ in range(20):
        ease = update_ease(ease, quality=3)
    assert ease == pytest.approx(settings.min_ease)


def test_interval_capped_at_max():
    state = SrsState(
        status=WordStatus.REVIEW,
        repetitions=20,
        ease=2.5,
        interval_days=settings.max_interval_days,
        due_at=NOW,
    )
    state = apply_answer(state, quality=5, now=NOW, rng=NO_JITTER)
    assert state.interval_days == settings.max_interval_days


def test_jitter_spreads_due_dates():
    state = SrsState(status=WordStatus.REVIEW, repetitions=5, ease=2.5, interval_days=10.0)
    dues = {
        apply_answer(state, quality=5, now=NOW, rng=random.Random(seed)).due_at
        for seed in range(20)
    }
    assert len(dues) > 1


def test_known_word_is_frozen():
    state = mark_known(NOW)
    assert apply_answer(state, quality=2, now=NOW, rng=NO_JITTER) == state


def test_exercise_rounds_are_fixed_and_skip_the_intro_card():
    # FR-006: порядок раундов задан спецификацией, один на оба режима занятия
    assert EXERCISE_ROUNDS == (
        ExerciseType.CHOICE_RU_EN,
        ExerciseType.CHOICE_EN_RU,
        ExerciseType.LETTERS,
        ExerciseType.DICTATION,
    )
    # FR-007: карточка-знакомство в раундах не участвует
    assert ExerciseType.INTRO not in EXERCISE_ROUNDS


def test_graduate_releases_a_word_without_touching_the_history():
    # FR-015b: занятие-изучение выпускает слово независимо от ошибок, поэтому
    # накопленные ease и lapses выпуск не трогает — наказывает только повторение
    state = SrsState(
        status=WordStatus.LEARNING, step=0, ease=2.3, lapses=2, due_at=NOW
    )

    released = graduate(state, now=NOW, rng=NO_JITTER)

    assert released.status is WordStatus.REVIEW
    assert released.repetitions == 1
    assert released.interval_days == FIRST_INTERVAL_DAYS
    assert released.due_at == NOW + timedelta(days=FIRST_INTERVAL_DAYS)
    assert (released.ease, released.lapses) == (state.ease, state.lapses)


@pytest.mark.parametrize(
    ("outcomes", "expected"),
    [
        # Безошибочное занятие с первого показа и без подсказок
        ([(True, False, 1), (True, False, 1), (True, False, 1), (True, False, 1)], 5),
        # Подсказка в одном раунде опускает итог до 4
        ([(True, False, 1), (True, True, 1), (True, False, 1), (True, False, 1)], 4),
        # Повторный показ весомее подсказки: 3
        ([(True, True, 1), (True, False, 2), (True, False, 1), (True, False, 1)], 3),
        # Любая ошибка за занятие означает «забыто», даже если её исправили
        ([(False, False, 1), (True, False, 2), (True, False, 1), (True, False, 1)], 2),
        # Одна попытка — оценка совпадает с обычной
        ([(True, False, 1)], 5),
    ],
)
def test_session_quality_is_the_worst_attempt(outcomes, expected):
    attempts = [
        AttemptOutcome(correct=c, used_hint=h, attempt=a) for c, h, a in outcomes
    ]
    assert session_quality(attempts) == expected


def test_forced_review_releases_a_word_without_a_schedule():
    state = force_status(start_learning(NOW), WordStatus.REVIEW, NOW, NO_JITTER)

    assert state.status == WordStatus.REVIEW
    assert state.repetitions == 1
    assert state.interval_days == FIRST_INTERVAL_DAYS
    assert state.due_at == NOW + timedelta(days=FIRST_INTERVAL_DAYS)


def test_forced_status_keeps_the_schedule_of_a_word_out_of_rotation():
    released = SrsState(
        status=WordStatus.REVIEW,
        repetitions=4,
        ease=2.3,
        interval_days=12.0,
        lapses=1,
        due_at=NOW + timedelta(days=12),
    )

    paused = force_status(released, WordStatus.SUSPENDED, NOW, NO_JITTER)
    assert paused.status == WordStatus.SUSPENDED

    back = force_status(paused, WordStatus.REVIEW, NOW, NO_JITTER)
    assert back == released


def test_forced_learning_returns_to_the_first_step_but_keeps_history():
    released = SrsState(
        status=WordStatus.REVIEW,
        repetitions=4,
        ease=2.3,
        interval_days=12.0,
        lapses=1,
        due_at=NOW + timedelta(days=12),
    )

    state = force_status(released, WordStatus.LEARNING, NOW, NO_JITTER)

    assert (state.status, state.step, state.due_at) == (WordStatus.LEARNING, 0, NOW)
    assert state.interval_days == 0.0
    # Ручная правка — не ответ: накопленную историю она не стирает
    assert (state.ease, state.lapses) == (2.3, 1)
