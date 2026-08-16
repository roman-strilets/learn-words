from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import ExerciseType

# --------------------------------------------------------------------------- слова


class WordBase(BaseModel):
    word: str = Field(min_length=1, max_length=128)
    translation: str = Field(min_length=1)
    example: str | None = None
    example_translation: str | None = None

    @field_validator("word", "translation")
    @classmethod
    def _strip_required(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("значение не может быть пустым")
        return v

    @field_validator("example", "example_translation")
    @classmethod
    def _strip_optional(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return v.strip() or None


class WordCreate(WordBase):
    pass


class WordUpdate(BaseModel):
    word: str | None = Field(default=None, min_length=1, max_length=128)
    translation: str | None = Field(default=None, min_length=1)
    example: str | None = None
    example_translation: str | None = None


class ProgressOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: str
    step: int
    repetitions: int
    ease: float
    interval_days: float
    due_at: datetime
    lapses: int


class WordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    word: str
    translation: str
    example: str | None
    example_translation: str | None
    created_at: datetime


class WordWithProgress(WordOut):
    progress: ProgressOut | None = None


class WordPage(BaseModel):
    items: list[WordWithProgress]
    total: int
    limit: int
    offset: int


# ---------------------------------------------------------------------- упражнения


class IntroExercise(BaseModel):
    type: Literal[ExerciseType.INTRO] = ExerciseType.INTRO
    word_id: int
    word: str
    translation: str
    example: str | None = None
    example_translation: str | None = None


class ChoiceRuEnExercise(BaseModel):
    """Показан русский перевод, надо выбрать английское слово."""

    type: Literal[ExerciseType.CHOICE_RU_EN] = ExerciseType.CHOICE_RU_EN
    word_id: int
    prompt: str
    options: list[str]
    hint: str | None = None


class ChoiceEnRuExercise(BaseModel):
    """Показано английское слово, надо выбрать перевод."""

    type: Literal[ExerciseType.CHOICE_EN_RU] = ExerciseType.CHOICE_EN_RU
    word_id: int
    prompt: str
    options: list[str]
    hint: str | None = None


class LettersExercise(BaseModel):
    """Собрать английское слово из букв. `mask` описывает раскладку ячеек:
    `_` — ячейка под букву, любой другой символ — фиксированный разделитель."""

    type: Literal[ExerciseType.LETTERS] = ExerciseType.LETTERS
    word_id: int
    prompt: str
    mask: str
    letters: list[str]
    show_letters: bool = True
    hint: str | None = None


class DictationExercise(BaseModel):
    """Слово произносится через Web Speech API, надо записать услышанное."""

    type: Literal[ExerciseType.DICTATION] = ExerciseType.DICTATION
    word_id: int
    audio_text: str
    hint: str


Exercise = Annotated[
    IntroExercise | ChoiceRuEnExercise | ChoiceEnRuExercise | LettersExercise | DictationExercise,
    Field(discriminator="type"),
]


# ------------------------------------------------------------------------- сессия


class SessionCounts(BaseModel):
    new: int
    learning: int
    review_due: int
    in_study: int


class SessionOut(BaseModel):
    """Стартовый набор сессии: сначала знакомство с новыми словами, потом очередь."""

    new_words: list[WordOut]
    exercises: list[Exercise]
    counts: SessionCounts


class SelectRequest(BaseModel):
    word_id: int
    action: Literal["learn", "know"]


class SelectResponse(BaseModel):
    progress: ProgressOut
    next_exercise: Exercise | None = None


class AnswerRequest(BaseModel):
    word_id: int
    exercise: ExerciseType
    answer: str | None = None
    used_hint: bool = False
    attempt: int = Field(default=1, ge=1)
    duration_ms: int | None = Field(default=None, ge=0)


class AnswerResponse(BaseModel):
    correct: bool
    correct_answer: str
    # Карточка слова целиком — плашка результата показывает её ещё раз
    word: str
    translation: str
    example: str | None = None
    example_translation: str | None = None
    quality: int
    repeat_in_session: bool
    next_exercise: Exercise | None = None
    progress: ProgressOut


# --------------------------------------------------------------------- статистика


class StatsOverview(BaseModel):
    total_words: int
    new: int
    learning: int
    review: int
    known: int
    due_now: int
    due_today: int
    answers_today: int
    new_today: int
    streak_days: int


class DailyStat(BaseModel):
    date: str
    answers: int
    correct: int
    accuracy: float
    new_words: int
