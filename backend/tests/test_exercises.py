"""Генерация упражнений, подбор дистракторов и проверка ответов."""

import random
from collections import Counter

import pytest
from sqlalchemy.orm import Session

from app.exercises import (
    build_exercise,
    build_letter_bank,
    build_mask,
    check_answer,
    correct_answer_for,
    normalize_answer,
    order_round,
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


def test_short_words_get_no_extra_letters():
    letters = build_letter_bank("flock", random.Random(1))
    assert sorted(letters) == sorted("FLOCK")


def test_letter_bank_order_is_stable_for_same_seed():
    assert build_letter_bank("scrutiny", random.Random(7)) == build_letter_bank(
        "scrutiny", random.Random(7)
    )


# ------------------------------------------------------------ порядок раунда


class _NoShuffle(random.Random):
    """Перемешивание, которое ничего не меняет: так запасные кандидаты срабатывают наверняка."""

    def shuffle(self, x) -> None:  # noqa: ARG002
        return None


@pytest.mark.parametrize("items", [[], [7]])
def test_order_round_keeps_zero_or_one_item_as_is(items: list[int]):
    assert order_round(items, items, items[-1] if items else None, random.Random(0)) == items


@pytest.mark.parametrize("n", [2, 3, 5])
@pytest.mark.parametrize("seed", range(200))
def test_order_round_differs_from_previous_and_avoids_last(n: int, seed: int):
    previous = list(range(n))

    result = order_round(previous, previous, previous[-1], random.Random(seed))

    assert sorted(result) == previous
    # FR-003: порядок раунда не повторяет предыдущий
    assert result != previous
    # FR-004: при 3 словах и больше раунд не начинается с последнего слова
    if n >= 3:
        assert result[0] != previous[-1]


def test_order_round_with_two_items_prefers_a_new_order_over_a_new_start():
    # FR-005: у двух слов второй порядок один, и он начинается с последнего слова
    for seed in range(50):
        assert order_round([0, 1], [0, 1], 1, random.Random(seed)) == [1, 0]


@pytest.mark.parametrize(
    ("items", "previous", "last", "expected"),
    [
        # Перемешанный порядок совпал с предыдущим раундом — меняем 1-е и 2-е
        ([0, 1, 2], [0, 1, 2], 2, [1, 0, 2]),
        # Начинается с последнего слова — меняем 1-е и 2-е
        ([2, 0, 1], [0, 1, 2], 2, [0, 2, 1]),
        # Обмен 1-го и 2-го дал бы предыдущий порядок — берём сдвиг
        ([2, 0, 1], [0, 2, 1], 2, [0, 1, 2]),
        # Совпал с предыдущим, а обмен и сдвиг начались бы с последнего — меняем 2-е и 3-е
        ([0, 2, 1], [0, 2, 1], 2, [0, 1, 2]),
    ],
)
def test_order_round_falls_back_to_the_next_candidate(
    items: list[int], previous: list[int], last: int, expected: list[int]
):
    assert order_round(items, previous, last, _NoShuffle()) == expected


def test_order_round_compares_by_key():
    items = [{"id": 1}, {"id": 2}, {"id": 3}]
    previous = [dict(item) for item in items]

    result = order_round(items, previous, previous[-1], _NoShuffle(), key=lambda x: x["id"])

    assert [x["id"] for x in result] == [2, 1, 3]
    assert [x["id"] for x in items] == [1, 2, 3]


def test_first_round_is_a_plain_shuffle():
    rng = random.Random(3)
    results = {tuple(order_round([0, 1, 2], None, None, rng)) for _ in range(200)}
    # Первый раунд ничем не ограничен: встречаются все шесть порядков
    assert len(results) == 6


def test_first_round_puts_every_item_first_equally_often():
    # SC-003: на первом месте каждое слово оказывается примерно в пятой части занятий
    rng = random.Random(0)
    firsts = Counter(order_round(list(range(5)), None, None, rng)[0] for _ in range(1_000))

    assert set(firsts) == set(range(5))
    assert all(150 <= count <= 250 for count in firsts.values())


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


def test_distractors_exclude_other_meanings_of_the_same_word(
    db_session: Session, words: list[Word]
):
    """У слова может быть несколько записей — в варианты ответа идёт одна."""
    target = next(w for w in words if w.word == "outsider")
    twin = Word(word="Outsider", word_key="outsider", translation="изгой")
    db_session.add(twin)
    db_session.flush()

    for _ in range(20):
        exercise = build_exercise(db_session, target, ExerciseType.CHOICE_RU_EN)
        assert exercise.options.count("outsider") == 1
        assert "Outsider" not in exercise.options


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


def test_writing_exercise_shows_translation_only(db_session: Session, words: list[Word]):
    target = next(w for w in words if w.word == "budge")
    exercise = build_exercise(db_session, target, ExerciseType.WRITING_RU_EN, rng=random.Random(0))

    assert exercise.type == ExerciseType.WRITING_RU_EN
    assert exercise.prompt == "сдвинуть с места"
    # FR-003: ни подсказки, ни ответа — в карточке нечего подсмотреть
    assert exercise.model_dump().keys() == {"type", "word_id", "prompt"}


@pytest.mark.parametrize(
    ("exercise_type", "answer", "expected"),
    [
        (ExerciseType.DICTATION, "budge", True),
        (ExerciseType.DICTATION, " BUDGE ", True),
        (ExerciseType.DICTATION, "to budge", True),
        (ExerciseType.DICTATION, "bulge", False),
        (ExerciseType.DICTATION, "", False),
        (ExerciseType.DICTATION, None, False),
        (ExerciseType.WRITING_RU_EN, "budge", True),
        (ExerciseType.WRITING_RU_EN, " BUDGE ", True),
        (ExerciseType.WRITING_RU_EN, "to budge", True),
        (ExerciseType.WRITING_RU_EN, "bulge", False),
        (ExerciseType.WRITING_RU_EN, "", False),
        (ExerciseType.WRITING_RU_EN, None, False),
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


def test_writing_rejects_a_synonym_with_the_same_translation(db_session: Session):
    big = Word(word="big", word_key="big", translation="большой")
    large = Word(word="large", word_key="large", translation="большой")
    db_session.add_all([big, large])
    db_session.flush()

    # Засчитывается только слово карточки, а после ответа видно, какое ждали
    assert check_answer(big, ExerciseType.WRITING_RU_EN, "large") is False
    assert correct_answer_for(big, ExerciseType.WRITING_RU_EN) == "big"


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


def test_repeat_card_reshuffles_the_letter_bank(db_session: Session, words: list[Word]):
    """FR-006a: повтор после ошибки — тот же тип, но карточка собрана заново.

    Маска и решение обязаны остаться прежними: меняется только порядок банка,
    иначе пользователь запоминает раскладку, а не слово.
    """
    target = next(w for w in words if w.word == "scrutiny")

    first = build_exercise(db_session, target, ExerciseType.LETTERS, attempt=1)
    second = build_exercise(db_session, target, ExerciseType.LETTERS, attempt=2)

    assert (second.mask, second.solution) == (first.mask, first.solution)
    assert sorted(second.letters) == sorted(first.letters)
    assert second.letters != first.letters
