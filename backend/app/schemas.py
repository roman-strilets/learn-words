from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import ExerciseType, WordStatus

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


class WordStatusUpdate(BaseModel):
    """Статус, выставленный вручную из словаря.

    `new` — единственное значение вне `WordStatus`: у нового слова строки
    прогресса нет, поэтому переход в него её удаляет.
    """

    status: WordStatus | Literal["new"]


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
    `_` — ячейка под букву, любой другой символ — фиксированный разделитель.

    `solution` — само слово: карточка не даёт поставить букву не на своё место,
    а для этого ей нужно знать ответ. Проверку это не подменяет — ответ всё
    равно проверяется на сервере, и «Показать ответ» по-прежнему засчитывается
    как ошибка. Диктант шлёт слово в браузер так же, ему нужна озвучка."""

    type: Literal[ExerciseType.LETTERS] = ExerciseType.LETTERS
    word_id: int
    prompt: str
    mask: str
    solution: str
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


class SessionMode(StrEnum):
    """Что делаем на занятии: знакомимся с новыми словами или повторяем изученные."""

    LEARN = "learn"
    REVIEW = "review"


class SessionCounts(BaseModel):
    new: int
    learning: int
    review_due: int
    in_study: int


class ReviewRound(BaseModel):
    """Раунд занятия-повторения: один тип упражнения на все слова занятия."""

    exercise: ExerciseType
    exercises: list[Exercise]


class SessionOut(BaseModel):
    """Стартовый набор сессии. Заполнена ровно одна из категорий: в режиме
    `learn` — новые слова на знакомство, в режиме `review` — план из раундов.

    `session_id` выдаётся только для повторения: это не серверное состояние,
    а ключ, по которому попытки занятия находят друг друга в `review_log`."""

    mode: SessionMode
    session_id: str | None = None
    new_words: list[WordOut]
    rounds: list[ReviewRound] = Field(default_factory=list)
    counts: SessionCounts


class SelectRequest(BaseModel):
    word_id: int
    action: Literal["learn", "know"]
    # Слова, уже показанные в этом занятии: замена не должна их повторять
    exclude_ids: list[int] = Field(default_factory=list)


class SelectResponse(BaseModel):
    progress: ProgressOut
    next_exercise: Exercise | None = None
    # Замена слову, помеченному «уже знаю», чтобы занятие осталось прежнего размера
    replacement: WordOut | None = None


class AnswerRequest(BaseModel):
    word_id: int
    exercise: ExerciseType
    answer: str | None = None
    used_hint: bool = False
    # Номер показа слова в текущем раунде: вторая и дальше снижают оценку
    attempt: int = Field(default=1, ge=1)
    duration_ms: int | None = Field(default=None, ge=0)
    mode: SessionMode = SessionMode.LEARN
    session_id: str | None = None

    @model_validator(mode="after")
    def _session_id_required_for_review(self) -> AnswerRequest:
        # Проверка на модели, а не на поле: пропущенный `session_id` берётся
        # из значения по умолчанию, а полевой валидатор на умолчание не зовут.
        # Без ключа занятия ответ повторения некуда записать, и `finish`
        # потом не соберёт итог — отказываем сразу, а не молча теряем попытку.
        if self.mode is SessionMode.REVIEW and not self.session_id:
            raise ValueError("session_id обязателен в режиме review")
        return self


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


class ReviewFinishRequest(BaseModel):
    session_id: str


class ReviewFinishResult(BaseModel):
    """Итог одного слова за занятие-повторение: что сервер вывел из журнала."""

    word_id: int
    mistakes: int
    quality: int
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
