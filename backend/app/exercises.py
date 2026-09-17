"""Сборка упражнений и проверка ответов.

Правильный ответ проверяется только здесь, на сервере: так он один для всех
типов упражнений и каждая попытка попадает в `review_log`.
"""

from __future__ import annotations

import random
import re
import unicodedata
from collections.abc import Callable, Hashable, Sequence

from rapidfuzz.distance import Levenshtein
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import ExerciseType, Word
from app.schemas import (
    ChoiceEnRuExercise,
    ChoiceRuEnExercise,
    DictationExercise,
    Exercise,
    LettersExercise,
)

OPTIONS_COUNT = 4
DISTRACTOR_POOL = 12

# Границы для порядка слов в раунде. Это не настройки, а следствие требований:
# одно слово переставлять некуда, а «не начинать с последнего слова» при двух
# словах противоречит «не повторять порядок» (FR-003, FR-004), поэтому
# в `app/config.py` они не выносятся.
MIN_WORDS_TO_REORDER = 2
MIN_WORDS_TO_AVOID_REPEAT = 3

# Артикли и частица `to` отбрасываются с обеих сторон сравнения:
# «to budge» и «budge» — один и тот же ответ.
_LEADING_PARTICLES = ("to ", "the ", "an ", "a ")
_DASHES = re.compile(r"[‐-―−]")
_APOSTROPHES = re.compile(r"[‘’ʼ`]")
_SEPARATORS = re.compile(r"[-_/]+")
_PUNCTUATION = re.compile(r"[^\w\s']", re.UNICODE)
_SPACES = re.compile(r"\s+")
_TRANSLATION_SPLIT = re.compile(r"[;,]")


def normalize_answer(text: str | None) -> str:
    """Привести ответ к канонической форме для сравнения.

    Приведение намеренно мягкое: дефисы и подчёркивания считаются пробелами,
    чтобы «out-of-town» и «out of town» засчитывались одинаково.
    """
    if not text:
        return ""
    value = unicodedata.normalize("NFKC", text).strip().lower()
    value = _APOSTROPHES.sub("'", value)
    value = _DASHES.sub("-", value)
    value = _SEPARATORS.sub(" ", value)
    value = _PUNCTUATION.sub(" ", value)
    value = _SPACES.sub(" ", value).strip()
    for particle in _LEADING_PARTICLES:
        if value.startswith(particle):
            return value[len(particle) :].strip()
    return value


def word_key_for(word: str) -> str:
    """Общий ключ всех записей одного слова: по нему они находят друг друга."""
    return _SPACES.sub(" ", word.strip().lower())


def translation_variants(translation: str) -> set[str]:
    """Отдельные значения слитого перевода («посторонний; чужак»)."""
    parts = {normalize_answer(p) for p in _TRANSLATION_SPLIT.split(translation)}
    parts.discard("")
    return parts or {normalize_answer(translation)}


# --------------------------------------------------------------- сборка из букв


def build_mask(word: str) -> str:
    """Раскладка ячеек: `_` — ячейка под букву, прочее — фиксированный разделитель.

    «go after» -> «__ _____»
    """
    return "".join("_" if ch.isalnum() else ch for ch in word)


def build_letter_bank(word: str, rng: random.Random) -> list[str]:
    """Буквы ответа — и только они — в перемешанном порядке."""
    letters = [ch.upper() for ch in word if ch.isalnum()]
    rng.shuffle(letters)
    return letters


def order_round[T](
    items: Sequence[T],
    previous: Sequence[T] | None,
    last: T | None,
    rng: random.Random,
    key: Callable[[T], Hashable] = lambda x: x,
) -> list[T]:
    """Случайный порядок слов раунда, не похожий на предыдущий раунд.

    Порядок отличается от `previous`, а при трёх словах и больше не начинается
    с `last` — слова, показанного последним. У двух слов второй порядок один,
    и он начинается с последнего слова: тогда важнее не повторить порядок.
    Для первого раунда (`previous is None`) — просто перемешивание.

    Вместо перемешивания «до удачи» перебираем четыре кандидата, и их всегда
    хватает. Пусть `q` — перемешанный порядок, `x = last`:
    - `q[0] == x`: обмен первых двух и сдвиг влево начинаются с `q[1] != x`
      и различны между собой, так что с `previous` совпадёт не больше одного;
    - `q[0] != x`, но `q == previous`: обмен 2-го и 3-го сохраняет начало
      и отличается от `q`, а значит и от `previous`;
    - два слова: обмен первых двух — единственный другой порядок.
    """
    shuffled = list(items)
    rng.shuffle(shuffled)
    if previous is None or len(shuffled) < MIN_WORDS_TO_REORDER:
        return shuffled

    previous_keys = [key(x) for x in previous]
    avoid_start = len(shuffled) >= MIN_WORDS_TO_AVOID_REPEAT and last is not None

    for candidate in _round_candidates(shuffled):
        if [key(x) for x in candidate] == previous_keys:
            continue
        if avoid_start and key(candidate[0]) == key(last):
            continue
        return candidate
    raise AssertionError("order_round: ни один кандидат не подошёл — ошибка в переборе")


def _round_candidates[T](q: list[T]) -> list[list[T]]:
    """Перемешанный порядок и три его запасные перестановки — ровно в этом порядке."""
    candidates = [q, [q[1], q[0], *q[2:]], [*q[1:], q[0]]]
    if len(q) >= MIN_WORDS_TO_AVOID_REPEAT:
        candidates.append([q[0], q[2], q[1], *q[3:]])
    return candidates


def _stable_rng(word_id: int, attempt: int) -> random.Random:
    """Одинаковый порядок букв при повторном запросе того же упражнения."""
    return random.Random(word_id * 1_000 + attempt)


# ------------------------------------------------------------------ дистракторы


def pick_distractor_words(
    session: Session,
    word: Word,
    *,
    count: int = OPTIONS_COUNT - 1,
    rng: random.Random | None = None,
) -> list[Word]:
    """Похожие слова для вариантов ответа.

    Случайные слова делают выбор слишком лёгким, поэтому кандидаты набираются
    по общему началу/окончанию и ранжируются расстоянием Левенштейна.
    """
    rng = rng or random.Random()
    key = word.word_key
    prefix = key[:3] if len(key) >= 4 else key[:1]
    suffix = key[-3:] if len(key) >= 4 else key[-1:]

    stmt = (
        select(Word)
        .where(Word.id != word.id)
        .where(or_(Word.word_key.like(f"{prefix}%"), Word.word_key.like(f"%{suffix}")))
        .limit(300)
    )
    candidates = list(session.scalars(stmt))

    if len(candidates) < DISTRACTOR_POOL:
        band = (
            select(Word)
            .where(Word.id != word.id)
            .where(func.length(Word.word_key).between(len(key) - 2, len(key) + 2))
            .order_by(func.random())
            .limit(100)
        )
        candidates += list(session.scalars(band))

    own_translations = translation_variants(word.translation)
    seen: set[int] = set()
    pool: list[Word] = []
    for candidate in candidates:
        if candidate.id in seen or candidate.word_key == key:
            continue
        # Два варианта с одинаковым переводом сделали бы задание нерешаемым.
        if translation_variants(candidate.translation) & own_translations:
            continue
        seen.add(candidate.id)
        pool.append(candidate)

    pool.sort(key=lambda c: Levenshtein.normalized_similarity(key, c.word_key), reverse=True)
    shortlist = pool[:DISTRACTOR_POOL]

    if len(shortlist) < count:
        filler = (
            select(Word)
            # `word_key` отсекает соседние значения того же слова: два одинаковых
            # варианта ответа в карточке выглядели бы опечаткой.
            .where(Word.id != word.id, Word.word_key != key, Word.id.notin_(seen or {0}))
            .order_by(func.random())
            .limit(count * 3)
        )
        for candidate in session.scalars(filler):
            if translation_variants(candidate.translation) & own_translations:
                continue
            shortlist.append(candidate)
            if len(shortlist) >= count:
                break

    if len(shortlist) <= count:
        return shortlist
    return rng.sample(shortlist, k=count)


# -------------------------------------------------------------------- упражнения


def first_letter_hint(word: str) -> str:
    """Подсказка под лампочкой: первая буква ответа."""
    for char in word:
        if char.isalnum():
            return f"Первая буква: {char.upper()}"
    return ""


def build_exercise(
    session: Session,
    word: Word,
    exercise_type: ExerciseType,
    *,
    show_letters: bool = True,
    attempt: int = 1,
    rng: random.Random | None = None,
) -> Exercise:
    rng = rng or random.Random()

    if exercise_type == ExerciseType.LETTERS:
        return LettersExercise(
            word_id=word.id,
            prompt=word.translation,
            mask=build_mask(word.word),
            solution=word.word,
            letters=build_letter_bank(word.word, _stable_rng(word.id, attempt)),
            show_letters=show_letters,
            hint=first_letter_hint(word.word),
        )

    if exercise_type == ExerciseType.DICTATION:
        return DictationExercise(
            word_id=word.id,
            audio_text=word.word,
            hint=word.translation,
        )

    distractors = pick_distractor_words(session, word, rng=rng)

    if exercise_type == ExerciseType.CHOICE_RU_EN:
        options = [word.word] + [d.word for d in distractors]
        rng.shuffle(options)
        return ChoiceRuEnExercise(
            word_id=word.id,
            prompt=word.translation,
            options=options,
            hint=first_letter_hint(word.word),
        )

    options = [word.translation] + [d.translation for d in distractors]
    rng.shuffle(options)
    # Для обратного направления полезнее пример употребления, если он есть.
    return ChoiceEnRuExercise(
        word_id=word.id,
        prompt=word.word,
        options=options,
        hint=word.example or first_letter_hint(word.translation),
    )


def correct_answer_for(word: Word, exercise_type: ExerciseType) -> str:
    """Что показать как правильный ответ после проверки."""
    if exercise_type == ExerciseType.CHOICE_EN_RU:
        return word.translation
    return word.word


def check_answer(word: Word, exercise_type: ExerciseType, answer: str | None) -> bool:
    # Знакомство — не проверка знания: на нём слово показывают, а не спрашивают.
    # Отсюда же следует, что упражнением его никогда не пересобирают: карточку
    # к повтору строят только после неверного ответа, а неверным он не бывает.
    if exercise_type == ExerciseType.INTRO:
        return True

    given = normalize_answer(answer)
    if not given:
        return False

    if exercise_type == ExerciseType.CHOICE_EN_RU:
        # Перевод мог быть слит из нескольких значений — засчитываем любое.
        return given in translation_variants(word.translation) or given == normalize_answer(
            word.translation
        )

    return given == normalize_answer(word.word)
