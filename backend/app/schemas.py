from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.models import ExerciseType, WordStatus

# --------------------------------------------------------------------------- слова

# Метка показывается чипом в строке словаря: длинное название её разорвало бы
LABEL_NAME_MAX = 50


def _label_name(v: str) -> str:
    v = v.strip()
    if not v:
        raise ValueError("название метки не может быть пустым")
    if len(v) > LABEL_NAME_MAX:
        raise ValueError(f"название метки длиннее {LABEL_NAME_MAX} символов")
    return v


# Название метки без крайних пробелов: и в форме слова, и на вкладке «Метки»
LabelName = Annotated[str, AfterValidator(_label_name)]


class LabelRef(BaseModel):
    """Метка в составе слова."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class LabelOut(BaseModel):
    """Метка в общем списке: со счётчиком слов для списка и для подтверждения удаления."""

    id: int
    name: str
    word_count: int


class LabelInput(BaseModel):
    """Новое название метки — при создании и при переименовании."""

    name: LabelName


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
    # Названия, а не id: новые метки создаются вместе со словом, в одной транзакции
    labels: list[LabelName] = Field(default_factory=list)


class WordUpdate(BaseModel):
    word: str | None = Field(default=None, min_length=1, max_length=128)
    translation: str | None = Field(default=None, min_length=1)
    example: str | None = None
    example_translation: str | None = None
    # `None` — метки не менять, `[]` — снять все
    labels: list[LabelName] | None = None


class WordStatusUpdate(BaseModel):
    """Статус, выставленный вручную из словаря.

    `new` — единственное значение вне `WordStatus`: у нового слова строки
    прогресса нет, поэтому переход в него её удаляет.
    """

    status: WordStatus | Literal["new"]


class WordPriorityUpdate(BaseModel):
    """Отметка «Учить первым», поставленная или снятая вручную из словаря.

    Это действие с очередью, а не правка текста и не ответ: в `review_log`
    оно не попадает."""

    priority: bool


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
    priority: bool
    # По названию без учёта регистра, «ё» = «е»
    labels: list[LabelRef] = Field(default_factory=list)


class WordWithProgress(WordOut):
    progress: ProgressOut | None = None


class WordPage(BaseModel):
    items: list[WordWithProgress]
    total: int
    limit: int
    offset: int


# ---------------------------------------------------------------------- упражнения


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


# Карточка-знакомство сюда не входит: знакомство идёт по слову целиком,
# до раундов, и упражнением никогда не приходит (FR-007)
Exercise = Annotated[
    ChoiceRuEnExercise | ChoiceEnRuExercise | LettersExercise | DictationExercise,
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


class ExerciseRound(BaseModel):
    """Раунд занятия: один тип упражнения на все слова занятия.

    Раунды одинаково устроены в обоих режимах, поэтому в имени нет ни
    «повторения», ни «изучения»."""

    exercise: ExerciseType
    exercises: list[Exercise]


class SessionOut(BaseModel):
    """Стартовый набор сессии. Заполнена ровно одна из категорий: в режиме
    `learn` — новые слова на знакомство, в режиме `review` — план из раундов.
    План изучения приходит отдельно, из `POST /study/rounds`: до конца
    знакомства неизвестно, какие слова в занятии останутся.

    `session_id` выдаётся в обоих режимах, когда занятию есть чем заняться:
    это не серверное состояние, а ключ, по которому попытки занятия находят
    друг друга в `review_log`."""

    mode: SessionMode
    session_id: str | None = None
    new_words: list[WordOut]
    rounds: list[ExerciseRound] = Field(default_factory=list)
    counts: SessionCounts


class RoundsRequest(BaseModel):
    """Слова, взятые в изучение по итогам знакомства.

    Пустой список — не ошибка: все слова могли оказаться уже знакомыми."""

    word_ids: list[int] = Field(default_factory=list)


class SelectRequest(BaseModel):
    word_id: int
    action: Literal["learn", "know"]
    # Слова, уже показанные в этом занятии: замена не должна их повторять
    exclude_ids: list[int] = Field(default_factory=list)


class SelectResponse(BaseModel):
    progress: ProgressOut
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
    def _session_id_is_required(self) -> AnswerRequest:
        # Проверка на модели, а не на поле: пропущенный `session_id` берётся
        # из значения по умолчанию, а полевой валидатор на умолчание не зовут.
        # Ключа занятия требуют оба режима: итог занятия сервер выводит из
        # журнала, и попытку без ключа он не найдёт — отказываем сразу,
        # а не теряем её молча.
        if not self.session_id:
            raise ValueError("session_id обязателен")
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


class SessionFinishRequest(BaseModel):
    session_id: str
    # Как выводить итог: повторение — по худшей попытке, изучение выпускает
    # слово независимо от ошибок. Из данных режим не вывести: слова в статусе
    # learning встречаются и в занятии-повторении, куда попадают после забывания
    mode: SessionMode


class SessionFinishResult(BaseModel):
    """Итог одного слова за занятие: что сервер вывел из журнала.

    В режиме `learn` `mistakes` остаётся информационным — на расписание он
    не влияет."""

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


# ---------------------------------------------------------------------- настройки


class NewWordsOrder(StrEnum):
    """В каком порядке «Изучение» берёт новые слова на знакомство.

    Касается только новых слов: «Повторение» идёт по сроку, и настраиваемый
    порядок там сломал бы интервальные повторения.
    """

    OLDEST_FIRST = "oldest_first"  # в порядке добавления в словарь
    NEWEST_FIRST = "newest_first"  # сначала недавно добавленные


class AppSettings(BaseModel):
    """Настройки приложения, которые меняются из интерфейса.

    В отличие от параметров алгоритма в `app/config.py`, их не правят руками
    в `backend/.env`: они лежат в таблице `settings` и действуют в любом браузере.
    Значения по умолчанию у поля нет, чтобы пустой `PUT` был ошибкой, а не сбросом.
    """

    new_words_order: NewWordsOrder
