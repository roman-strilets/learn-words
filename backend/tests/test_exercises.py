"""Генерация упражнений, подбор дистракторов и проверка ответов."""

import random

import pytest
from sqlalchemy.orm import Session

from app.exercises import (
    build_exercise,
    build_letter_bank,
    build_mask,
    check_answer,
    normalize_answer,
    pick_distractor_words,
    translation_variants,
    word_key_for,
)
from app.models import ExerciseType, Word


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  The Outsider ", "outsider"),
        ("OUT-OF-TOWN", "out of town"),
        ("out of town", "out of town"),
        ("to budge", "budge"),
        ("a lot", "lot"),
        ("don’t", "don't"),
        ("go   after", "go after"),
        ("", ""),
        (None, ""),
    ],
)
def test_normalize_answer(raw, expected):
    assert normalize_answer(raw) == expected


def test_solution_lines_up_with_mask(db_session: Session, words: list[Word]):
    """Карточка сверяет ввод по `solution[i]` для ячейки `mask[i]` —
    строки обязаны совпадать по длине и по расположению разделителей."""
    rng = random.Random(0)
    for word in words:
        exercise = build_exercise(db_session, word, ExerciseType.LETTERS, rng=rng)
        assert exercise.solution == word.word
        assert len(exercise.mask) == len(exercise.solution)
        for cell, char in zip(exercise.mask, exercise.solution, strict=True):
            # Ячейка под букву — там, где в слове буква или цифра, и только там
            assert (cell == "_") == char.isalnum()

        # Банк покрывает каждую ячейку: собрать слово целиком возможно
        bank = sorted(exercise.letters)
        needed = sorted(c.upper() for c in exercise.solution if c.isalnum())
        for letter in needed:
            assert letter in bank
            bank.remove(letter)


def test_mask_keeps_separators():
    # Как на скриншоте: две ячейки, пробел, пять ячеек
    assert build_mask("go after") == "__ _____"
    assert build_mask("out-of-town") == "___-__-____"
    assert build_mask("budge") == "_____"


def test_letter_bank_contains_all_answer_letters():
    letters = build_letter_bank("go after", random.Random(1))
    assert sorted(letters) == sorted("GOAFTER")


def test_short_words_get_extra_letters():
    letters = build_letter_bank("budge", random.Random(1))
    assert len(letters) == len("budge") + 2
    for char in "BUDGE":
        assert char in letters


def test_letter_bank_order_is_stable_for_same_seed():
    assert build_letter_bank("scrutiny", random.Random(7)) == build_letter_bank(
        "scrutiny", random.Random(7)
    )


def test_translation_variants_splits_merged_translation():
    assert translation_variants("посторонний; чужак") == {"посторонний", "чужак"}


def test_word_key_normalizes_case_and_spaces():
    assert word_key_for("  Go   After ") == "go after"


def test_distractors_are_similar_and_unique(db_session: Session, words: list[Word]):
    target = next(w for w in words if w.word == "outsider")
    distractors = pick_distractor_words(db_session, target, rng=random.Random(0))

    assert len(distractors) == 3
    assert target.id not in {d.id for d in distractors}
    assert len({d.id for d in distractors}) == 3
    # Кандидаты набираются по общему началу/окончанию, а не случайно
    assert any(d.word.startswith("out") or d.word.endswith("out") for d in distractors)


def test_distractors_exclude_same_translation(db_session: Session, words: list[Word]):
    target = next(w for w in words if w.word == "outsider")
    twin = Word(word="bystander", word_key="bystander", translation="посторонний")
    db_session.add(twin)
    db_session.flush()

    distractors = pick_distractor_words(db_session, target, rng=random.Random(0))
    assert twin.id not in {d.id for d in distractors}


def test_choice_exercise_contains_correct_option(db_session: Session, words: list[Word]):
    target = next(w for w in words if w.word == "outsider")
    exercise = build_exercise(
        db_session, target, ExerciseType.CHOICE_RU_EN, rng=random.Random(0)
    )

    assert exercise.prompt == "посторонний"
    assert exercise.options.count("outsider") == 1
    assert len(exercise.options) == 4


def test_letters_exercise_uses_mask_and_bank(db_session: Session, words: list[Word]):
    target = next(w for w in words if w.word == "go after")
    exercise = build_exercise(db_session, target, ExerciseType.LETTERS, rng=random.Random(0))

    assert exercise.mask == "__ _____"
    assert sorted(exercise.letters) == sorted("GOAFTER")
    assert exercise.prompt == "преследовать"


def test_dictation_exercise_carries_audio_and_hint(db_session: Session, words: list[Word]):
    target = next(w for w in words if w.word == "budge")
    exercise = build_exercise(db_session, target, ExerciseType.DICTATION, rng=random.Random(0))

    assert exercise.audio_text == "budge"
    assert exercise.hint == "сдвинуть с места"


@pytest.mark.parametrize(
    ("exercise_type", "answer", "expected"),
    [
        (ExerciseType.DICTATION, "budge", True),
        (ExerciseType.DICTATION, " BUDGE ", True),
        (ExerciseType.DICTATION, "to budge", True),
        (ExerciseType.DICTATION, "bulge", False),
        (ExerciseType.DICTATION, "", False),
        (ExerciseType.DICTATION, None, False),
        (ExerciseType.LETTERS, "BUDGE", True),
        (ExerciseType.CHOICE_RU_EN, "budge", True),
        (ExerciseType.CHOICE_EN_RU, "сдвинуть с места", True),
        (ExerciseType.CHOICE_EN_RU, "край", False),
        (ExerciseType.INTRO, None, True),
    ],
)
def test_check_answer(db_session: Session, words: list[Word], exercise_type, answer, expected):
    target = next(w for w in words if w.word == "budge")
    assert check_answer(target, exercise_type, answer) is expected


def test_check_answer_accepts_any_merged_translation(db_session: Session):
    word = Word(word="patty", word_key="patty", translation="котлета; лепешечка")
    db_session.add(word)
    db_session.flush()

    assert check_answer(word, ExerciseType.CHOICE_EN_RU, "котлета") is True
    assert check_answer(word, ExerciseType.CHOICE_EN_RU, "лепешечка") is True
    assert check_answer(word, ExerciseType.CHOICE_EN_RU, "котлета; лепешечка") is True
    assert check_answer(word, ExerciseType.CHOICE_EN_RU, "суп") is False


def test_hints_are_filled_per_exercise_type(db_session: Session, words: list[Word]):
    import random as _random

    target = next(w for w in words if w.word == "go after")
    rng = _random.Random(0)

    choice_ru_en = build_exercise(db_session, target, ExerciseType.CHOICE_RU_EN, rng=rng)
    letters = build_exercise(db_session, target, ExerciseType.LETTERS, rng=rng)
    choice_en_ru = build_exercise(db_session, target, ExerciseType.CHOICE_EN_RU, rng=rng)

    assert choice_ru_en.hint == "Первая буква: G"
    assert letters.hint == "Первая буква: G"
    # Подсказка не должна раскрывать сам ответ
    assert target.word not in (choice_ru_en.hint or "")
    # Для EN→RU полезнее пример, а при его отсутствии — первая буква перевода
    assert choice_en_ru.hint == "Первая буква: П"


def test_hint_uses_example_when_available(db_session: Session):
    word = Word(
        word="brink",
        word_key="brink",
        translation="край",
        example="Pushed to the brink.",
    )
    db_session.add(word)
    db_session.flush()

    exercise = build_exercise(db_session, word, ExerciseType.CHOICE_EN_RU, rng=random.Random(0))
    assert exercise.hint == "Pushed to the brink."
