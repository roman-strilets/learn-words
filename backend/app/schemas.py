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

from app.config import settings
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

# Описание — пояснение темы для модели, а не текст: пары фраз хватает
LABEL_DESCRIPTION_MAX = 200


def _label_description(v: str | None) -> str | None:
    """Пустое описание и его отсутствие — одно и то же, `None`."""
    if v is None:
        return None
    v = v.strip()
    if len(v) > LABEL_DESCRIPTION_MAX:
        raise ValueError(f"описание метки длиннее {LABEL_DESCRIPTION_MAX} символов")
    return v or None


LabelDescription = Annotated[str | None, AfterValidator(_label_description)]


class LabelRef(BaseModel):
    """Метка в составе слова."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class LabelOut(BaseModel):
    """Метка в общем списке: со счётчиком слов для списка и для подтверждения удаления."""

    id: int
    name: str
    description: str | None
    word_count: int


class LabelInput(BaseModel):
    """Новая метка."""

    name: LabelName
    description: LabelDescription = None


class LabelUpdate(BaseModel):
    """Частичная правка метки: меняются только переданные поля.

    Поэтому переименование `{name}` не стирает описание.
    """

    name: LabelName | None = None
    description: LabelDescription = None

    @model_validator(mode="after")
    def _something_to_change(self) -> LabelUpdate:
        if not self.model_fields_set:
            raise ValueError("нечего менять: передайте name или description")
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("название метки не может быть пустым")
        return self


# Предел слова в форме; импорт CSV пропускает строки длиннее — так он не заводит
# записей, которые форма потом не дала бы сохранить
WORD_MAX_LENGTH = 128


class WordBase(BaseModel):
    word: str = Field(min_length=1, max_length=WORD_MAX_LENGTH)
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
    word: str | None = Field(default=None, min_length=1, max_length=WORD_MAX_LENGTH)
    translation: str | None = Field(default=None, min_length=1)
    example: str | None = None
    example_translation: str | None = None
    # `None` — метки не менять, `[]` — снять все
    labels: list[LabelName] | None = None


# Фраза длиннее слова: «once in a blue moon», «It's up to you» и целые
# предложения. 200 — с запасом под реплику, но без абзацев
PHRASE_MAX_LENGTH = 200


class PhraseCreate(WordCreate):
    """Новая фраза: те же поля, что у слова, `word` — текст фразы."""

    word: str = Field(min_length=1, max_length=PHRASE_MAX_LENGTH)


class PhraseUpdate(WordUpdate):
    word: str | None = Field(default=None, min_length=1, max_length=PHRASE_MAX_LENGTH)


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


# ---------------------------------------------------------------- импорт из CSV


class ImportSkippedRow(BaseModel):
    """Строка файла, пропущенная при импорте: номер как в табличном редакторе и причина."""

    line: int
    reason: str


class ImportReport(BaseModel):
    """Итог одного импорта CSV. Нигде не хранится: показывается сразу после импорта.

    Счётчики считают строки файла, а не записи словаря, и каждая строка попадает
    ровно в один: `rows == created + merged + unchanged + skipped`. В
    `skipped_rows` — не больше `import_skipped_report_max` пропусков, полное их
    число — в `skipped`.
    """

    rows: int
    created: int
    merged: int
    unchanged: int
    skipped: int
    skipped_rows: list[ImportSkippedRow]
    labels_created: list[str]
    ignored_columns: list[str]


# ----------------------------------------------------------------------- разметка


class ClassifyRequest(BaseModel):
    """Одна пачка автоматической разметки.

    Пачка — одно звено цепочки независимых запросов: сервер не помнит этап,
    фронт передаёт курсор `from_id` из ответа предыдущей пачки. Фильтры — те же,
    что у `GET /words`, и значат то же самое.
    """

    search: str | None = None
    status: str | None = None
    priority: bool | None = None
    # id метки или `none`; число принимается, чтобы фронт мог передать id как есть
    label: str | None = None
    label_ids: list[int] = Field(min_length=1)
    from_id: int | None = Field(default=None, ge=1)
    limit: int

    @field_validator("label", mode="before")
    @classmethod
    def _label_as_text(cls, v: object) -> object:
        return str(v) if isinstance(v, int) and not isinstance(v, bool) else v

    @field_validator("limit")
    @classmethod
    def _limit_in_range(cls, v: int) -> int:
        if not 1 <= v <= settings.classifier_batch_max:
            raise ValueError(f"размер пачки — от 1 до {settings.classifier_batch_max}")
        return v


class ClassifyResult(BaseModel):
    """Итог по слову. `added` — метка поставлена этим запросом, а не стояла раньше."""

    word_id: int
    word: str
    translation: str
    label: LabelRef | None
    added: bool


# Пределы длины — с запасом на облачные адреса и ключи; модели называются коротко
CLASSIFIER_URL_MAX = 512
CLASSIFIER_KEY_MAX = 512
CLASSIFIER_MODEL_MAX = 128


class ClassifierInput(BaseModel):
    """Подключение к классификатору: адрес сервиса, ключ доступа и модель."""

    base_url: str
    api_key: str
    model: str

    @field_validator("base_url")
    @classmethod
    def _url(cls, v: str) -> str:
        v = v.strip()
        if len(v) > CLASSIFIER_URL_MAX:
            raise ValueError(f"адрес длиннее {CLASSIFIER_URL_MAX} символов")
        if not v.startswith(("http://", "https://")) or v in {"http://", "https://"}:
            raise ValueError("адрес должен начинаться с http:// или https://")
        return v

    @field_validator("api_key")
    @classmethod
    def _key(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("ключ доступа не может быть пустым")
        if len(v) > CLASSIFIER_KEY_MAX:
            raise ValueError(f"ключ длиннее {CLASSIFIER_KEY_MAX} символов")
        # Иначе его отклонит SDK — лучше сказать об этом при сохранении
        if not v.isascii() or not v.isprintable() or " " in v:
            raise ValueError("ключ — только латиница, цифры и знаки, без пробелов")
        return v

    @field_validator("model")
    @classmethod
    def _model(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("модель не может быть пустой")
        if len(v) > CLASSIFIER_MODEL_MAX:
            raise ValueError(f"название модели длиннее {CLASSIFIER_MODEL_MAX} символов")
        return v


class ClassifierSettings(ClassifierInput):
    """Действующее подключение. `is_default` — ничего не сохранено, всё из `config.py`."""

    is_default: bool


class ClassifierCheck(BaseModel):
    """Итог «Проверить подключение»: неудача — ответ, а не ошибка запроса."""

    ok: bool
    detail: str


class ClassifyBatch(BaseModel):
    """Ответ пачки: результаты по `id` и курсор следующей.

    `skipped` — слова, удалённые, пока модель думала. `next_from_id` — `null`,
    если подходящих слов дальше нет. `remaining` — сколько их с `id ≥ next_from_id`.
    """

    results: list[ClassifyResult]
    skipped: int
    next_from_id: int | None
    remaining: int


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


class WritingRuEnExercise(BaseModel):
    """Показан русский перевод, надо написать английское слово. Подсказки и ответа
    в карточке нет: вспомнить слово без опоры — и есть задание."""

    type: Literal[ExerciseType.WRITING_RU_EN] = ExerciseType.WRITING_RU_EN
    word_id: int
    prompt: str


class DictationExercise(BaseModel):
    """Слово произносится через Web Speech API, надо записать услышанное."""

    type: Literal[ExerciseType.DICTATION] = ExerciseType.DICTATION
    word_id: int
    audio_text: str
    hint: str


# Карточка-знакомство сюда не входит: знакомство идёт по слову целиком,
# до раундов, и упражнением никогда не приходит (FR-007)
Exercise = Annotated[
    ChoiceRuEnExercise
    | ChoiceEnRuExercise
    | LettersExercise
    | WritingRuEnExercise
    | DictationExercise,
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


# ------------------------------------------------------------ занятие по группе


class GroupOut(BaseModel):
    """Метка слов в выборе группы: сколько в ней слов и где она в своём круге."""

    label_id: int
    name: str
    # Члены группы в любом статусе, с прогрессом и без
    word_count: int
    # Пройдено в текущем круге, 0..word_count
    done: int
    # Номер текущего круга; 0 — по группе ещё не занимались
    cycle: int


class GroupSessionRequest(BaseModel):
    label_id: int


class GroupSessionOut(BaseModel):
    """Порция группы: те же пять раундов, что у повторения, без знакомства.

    `session_id` — ключ, по которому `finish` найдёт попытки порции в
    `group_review_log`; `None`, когда в группе нет слов и занятия нет."""

    label_id: int
    name: str
    session_id: str | None = None
    rounds: list[ExerciseRound] = Field(default_factory=list)
    word_count: int
    # Пройдено в текущем круге до этого занятия
    done: int
    cycle: int


class GroupAnswerRequest(BaseModel):
    """Ответ на карточку занятия по группе. Метка нужна, чтобы отказать слову,
    с которого её сняли посреди занятия, и записать её в журнал."""

    word_id: int
    label_id: int
    session_id: str
    exercise: ExerciseType
    answer: str | None = None
    used_hint: bool = False
    attempt: int = Field(default=1, ge=1)
    duration_ms: int | None = Field(default=None, ge=0)

    @field_validator("exercise")
    @classmethod
    def _no_intro(cls, v: ExerciseType) -> ExerciseType:
        # Знакомства в занятии по группе нет: засчитать его — значит засчитать
        # слово без вопроса
        if v is ExerciseType.INTRO:
            raise ValueError("В занятии по группе знакомства нет")
        return v


class GroupAnswerResponse(BaseModel):
    """Те же поля, что у `AnswerResponse`, кроме прогресса: занятие по группе
    его не читает и не меняет."""

    correct: bool
    correct_answer: str
    word: str
    translation: str
    example: str | None = None
    example_translation: str | None = None
    quality: int
    repeat_in_session: bool
    next_exercise: Exercise | None = None


class GroupFinishRequest(BaseModel):
    session_id: str


class GroupFinishResult(BaseModel):
    """Слово, прошедшее все раунды порции: оно отмечено пройденным в своём круге."""

    word_id: int
    mistakes: int


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
