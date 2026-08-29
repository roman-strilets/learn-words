"""Расписание повторений: шаги знакомства и SM-2."""

import random
from datetime import datetime, timedelta

import pytest

from app.config import settings
from app.models import ExerciseType, WordStatus
from app.srs import (
    FIRST_INTERVAL_DAYS,
    LEARNING_STEPS,
    RELEARN_STEP,
    SrsState,
    apply_answer,
    derive_quality,
    exercise_for,
    force_status,
    mark_known,
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


def test_learning_steps_run_in_order():
    state = start_learning(NOW)
    seen = []
    for _ in LEARNING_STEPS:
        seen.append(exercise_for(state))
        state = apply_answer(state, quality=5, now=NOW, rng=NO_JITTER)

    assert seen == [
        ExerciseType.INTRO,
        ExerciseType.CHOICE_RU_EN,
        ExerciseType.LETTERS,
        ExerciseType.DICTATION,
    ]
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
    state = SrsState(status=WordStatus.LEARNING, step=len(LEARNING_STEPS) - 1, due_at=NOW)
    state = apply_answer(state, quality=5, now=NOW, rng=NO_JITTER)

    assert state.status is WordStatus.REVIEW
    assert state.repetitions == 1
    assert state.interval_days == 1.0
    assert state.due_at == NOW + timedelta(days=1)


def test_review_intervals_grow():
    state = start_learning(NOW)
    for _ in LEARNING_STEPS:
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


def test_review_exercises_never_include_intro():
    rng = random.Random(0)
    state = SrsState(status=WordStatus.REVIEW, repetitions=3, due_at=NOW)
    picked = {exercise_for(state, rng) for _ in range(50)}
    assert ExerciseType.INTRO not in picked
    assert len(picked) > 1


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
