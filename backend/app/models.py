from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    false,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, synonym

from app.clock import utcnow
from app.db import Base


class WordStatus(StrEnum):
    """Состояние слова в изучении.

    NEW не хранится в базе: у нового слова просто нет строки в `progress`.
    """

    LEARNING = "learning"  # проходит шаги первого знакомства
    REVIEW = "review"  # выпущено, планируется по SM-2
    KNOWN = "known"  # помечено «уже знаю», не показывается
    SUSPENDED = "suspended"  # отложено вручную


class ExerciseType(StrEnum):
    INTRO = "intro"
    CHOICE_RU_EN = "choice_ru_en"
    CHOICE_EN_RU = "choice_en_ru"
    LETTERS = "letters"
    WRITING_RU_EN = "writing_ru_en"
    DICTATION = "dictation"


# Связка «слово — метка». Каскады на обоих концах снимают метку со всех слов
# при её удалении и метки слова при удалении слова — без кода в сервисе.
# Составной ключ начинается с `word_id`, а фильтру и счётчику нужен поиск по
# `label_id` — отсюда отдельный индекс.
word_labels = Table(
    "word_labels",
    Base.metadata,
    Column("word_id", ForeignKey("words.id", ondelete="CASCADE"), primary_key=True),
    Column("label_id", ForeignKey("labels.id", ondelete="CASCADE"), primary_key=True),
    Index("ix_word_labels_label_id", "label_id"),
)


class Label(Base):
    """Тематическая метка словаря («кухня», «глаголы движения»).

    Метка существует независимо от слов: у неё может не быть ни одной связки.
    `name_key` считается в Python (`labels_service.label_key`), потому что
    `lower()` и `NOCASE` в SQLite не знают кириллицы: «Кухня» и «кухня» для
    них разные строки.

    `description` — необязательное пояснение темы для автоматической разметки:
    классификатор берёт его критерием вместо названия.
    """

    __tablename__ = "labels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    name_key: Mapped[str] = mapped_column(String(50), nullable=False)
    # Короткое «B2» модель поймёт хуже, чем «advanced vocabulary (CEFR B2)»
    description: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    __table_args__ = (Index("ux_labels_name_key", "name_key", unique=True),)

    def __repr__(self) -> str:
        return f"<Label {self.id} {self.name!r}>"


class Word(Base):
    __tablename__ = "words"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    word: Mapped[str] = mapped_column(String(128), nullable=False)
    # lower(trim(word)) — общий ключ всех значений одного слова
    word_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    translation: Mapped[str] = mapped_column(Text, nullable=False)
    example: Mapped[str | None] = mapped_column(Text, nullable=True)
    example_translation: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    # Отметка «Учить первым»: поднимает слово в очереди «Изучения». Бывает только
    # у слова без прогресса и снимается, как только прогресс появляется
    priority: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )

    progress: Mapped["Progress | None"] = relationship(
        back_populates="word",
        cascade="all, delete-orphan",
        uselist=False,
        lazy="selectin",
    )
    # Порядок тот же, что у `labels_service.label_sort_key`: по ключу, «ё» = «е»
    labels: Mapped[list[Label]] = relationship(
        secondary=word_labels,
        lazy="selectin",
        order_by=func.replace(Label.name_key, "ё", "е"),
    )

    # Слово можно завести несколько раз — по записи на каждое значение
    # («roll out» = «вылезать» и «внедрить»): у значений разный прогресс,
    # и каждое учится само по себе. Повторять уже заведённое значение незачем.
    __table_args__ = (
        Index("ux_words_word_key_translation", "word_key", "translation", unique=True),
    )

    def __repr__(self) -> str:
        return f"<Word {self.id} {self.word!r}>"


class Progress(Base):
    """Прогресс по слову. Строка появляется, когда слово взято в изучение."""

    __tablename__ = "progress"

    word_id: Mapped[int] = mapped_column(
        ForeignKey("words.id", ondelete="CASCADE"), primary_key=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=WordStatus.LEARNING)
    # индекс шага первого знакомства; актуален только при status = learning
    step: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    repetitions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ease: Mapped[float] = mapped_column(Float, nullable=False, default=2.5)
    interval_days: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    due_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    lapses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )

    word: Mapped[Word] = relationship(back_populates="progress")

    __table_args__ = (Index("ix_progress_status_due_at", "status", "due_at"),)

    def __repr__(self) -> str:
        return f"<Progress word={self.word_id} {self.status} step={self.step} due={self.due_at}>"


class ReviewLog(Base):
    """По строке на каждый ответ: нужен для статистики и для перехода на FSRS."""

    __tablename__ = "review_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    word_id: Mapped[int] = mapped_column(
        ForeignKey("words.id", ondelete="CASCADE"), nullable=False, index=True
    )
    exercise: Mapped[str] = mapped_column(String(24), nullable=False)
    correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    used_hint: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    quality: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status_before: Mapped[str] = mapped_column(String(16), nullable=False)
    status_after: Mapped[str] = mapped_column(String(16), nullable=False)
    ease_after: Mapped[float] = mapped_column(Float, nullable=False)
    interval_after: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False, index=True
    )
    # Ключ занятия-повторения: по нему `finish` собирает все попытки занятия
    # и выводит итог. NULL — ответ вне занятия-повторения (режим «Изучение»
    # и все строки, накопленные до появления раундов).
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)


# ------------------------------------------------------------ занятие по группе
#
# Занятие по группе (по метке слов) не трогает основное обучение: ни `progress`,
# ни `review_log`, ни статистику. Поэтому у него свои таблицы — круг группы
# и журнал ответов (research R1, R2).


class GroupCycleWord(Base):
    """Место одного слова в одном круге одной метки.

    Строка на (метка, круг, слово), а не одна на (метка, слово): порядок круга
    фиксируется один раз и переживает перезагрузку и прерванное занятие, а на
    стыке кругов слову нужны сразу две позиции — в остатке текущего круга и в
    уже выбранном порядке следующего (research R2). Живут не больше двух кругов
    метки; старшие удаляет сборка занятия. Строки слова, потерявшего метку, не
    удаляются: вернётся метка — вернётся и место в круге (research R5).
    """

    __tablename__ = "group_cycle_words"

    label_id: Mapped[int] = mapped_column(
        ForeignKey("labels.id", ondelete="CASCADE"), primary_key=True
    )
    cycle: Mapped[int] = mapped_column(Integer, primary_key=True)
    word_id: Mapped[int] = mapped_column(
        ForeignKey("words.id", ondelete="CASCADE"), primary_key=True
    )
    # Место в порядке круга, с 0; слова, получившие метку позже, — в конец
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    # Когда слово прошло все раунды в этом круге; NULL — ещё не пройдено
    done_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Ключ занятия, которым слово пройдено: повторный `finish` не закроет ему
    # ещё и следующий круг (research R6)
    done_session_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    # Ключ начинается с `label_id`; каскаду удаления слова нужен поиск по `word_id`
    __table_args__ = (Index("ix_group_cycle_words_word_id", "word_id"),)


class GroupReviewLog(Base):
    """По строке на каждый ответ в занятии по группе.

    Отдельно от `review_log`, чтобы статистика и `finish` обычных занятий не
    видели групповых попыток без единого фильтра. Колонок расписания нет: в
    занятии по группе переходов расписания не бывает, а у нового слова нет и
    статуса (research R1).
    """

    __tablename__ = "group_review_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    word_id: Mapped[int] = mapped_column(
        ForeignKey("words.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # NULL — метку удалили потом: попытки остаются и в обычные не превращаются
    label_id: Mapped[int | None] = mapped_column(
        ForeignKey("labels.id", ondelete="SET NULL"), nullable=True
    )
    exercise: Mapped[str] = mapped_column(String(24), nullable=False)
    correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    used_hint: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # Оценка по `derive_quality` — для будущей статистики групп, расписания не меняет
    quality: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False, index=True
    )


# --------------------------------------------------------------------- фразы
#
# Фразы — вторая колода со своим словарём, метками, прогрессом и журналом.
# Таблицы отдельные, а не колонка «вид записи» у `words`: запрос по словам
# не может вернуть фразу, `finish` по `review_log` не может пересчитать фразу,
# и счётчики статистики слов не зависят от фраз (research R1).
#
# Общий код занятия работает с обеими колодами через описание колоды
# (`app/decks.py`). Чтобы он и общие схемы читали фразу теми же именами, что
# слово, у моделей фраз есть синонимы: `word → text`, `word_key → text_key`,
# `word_id → phrase_id` (research R2). Имена колонок в базе остаются честными.


# Связка «фраза — метка фраз»; каскады и индекс — как у `word_labels`
phrase_label_links = Table(
    "phrase_label_links",
    Base.metadata,
    Column("phrase_id", ForeignKey("phrases.id", ondelete="CASCADE"), primary_key=True),
    Column(
        "label_id", ForeignKey("phrase_labels.id", ondelete="CASCADE"), primary_key=True
    ),
    Index("ix_phrase_label_links_label_id", "label_id"),
)


class PhraseLabel(Base):
    """Метка фраз. Те же поля, что у `Label`, но своя таблица: метка фраз и
    метка слов с одинаковым названием — разные метки."""

    __tablename__ = "phrase_labels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    name_key: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    __table_args__ = (Index("ux_phrase_labels_name_key", "name_key", unique=True),)

    def __repr__(self) -> str:
        return f"<PhraseLabel {self.id} {self.name!r}>"


class Phrase(Base):
    """Фраза — английское выражение из нескольких слов с переводом."""

    __tablename__ = "phrases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(String(200), nullable=False)
    # lower + схлопнутые пробелы — ключ дубля, как `Word.word_key`
    text_key: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    translation: Mapped[str] = mapped_column(Text, nullable=False)
    example: Mapped[str | None] = mapped_column(Text, nullable=True)
    example_translation: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    # «Учить первой»: бывает только у фразы без прогресса
    priority: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )

    # Имена слова для общего кода занятия и схем `WordOut`
    word = synonym("text")
    word_key = synonym("text_key")

    progress: Mapped["PhraseProgress | None"] = relationship(
        back_populates="phrase",
        cascade="all, delete-orphan",
        uselist=False,
        lazy="selectin",
    )
    labels: Mapped[list[PhraseLabel]] = relationship(
        secondary=phrase_label_links,
        lazy="selectin",
        order_by=func.replace(PhraseLabel.name_key, "ё", "е"),
    )

    __table_args__ = (
        Index("ux_phrases_text_key_translation", "text_key", "translation", unique=True),
    )

    def __repr__(self) -> str:
        return f"<Phrase {self.id} {self.text!r}>"


class PhraseProgress(Base):
    """Прогресс по фразе — те же колонки и смысл, что у `Progress`."""

    __tablename__ = "phrase_progress"

    phrase_id: Mapped[int] = mapped_column(
        ForeignKey("phrases.id", ondelete="CASCADE"), primary_key=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=WordStatus.LEARNING)
    step: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    repetitions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ease: Mapped[float] = mapped_column(Float, nullable=False, default=2.5)
    interval_days: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    due_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    lapses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )

    word_id = synonym("phrase_id")

    phrase: Mapped[Phrase] = relationship(back_populates="progress")

    __table_args__ = (Index("ix_phrase_progress_status_due_at", "status", "due_at"),)

    def __repr__(self) -> str:
        return (
            f"<PhraseProgress phrase={self.phrase_id} {self.status} "
            f"step={self.step} due={self.due_at}>"
        )


class PhraseReviewLog(Base):
    """Журнал ответов по фразам — те же колонки, что у `ReviewLog`."""

    __tablename__ = "phrase_review_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    phrase_id: Mapped[int] = mapped_column(
        ForeignKey("phrases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    exercise: Mapped[str] = mapped_column(String(24), nullable=False)
    correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    used_hint: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    quality: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status_before: Mapped[str] = mapped_column(String(16), nullable=False)
    status_after: Mapped[str] = mapped_column(String(16), nullable=False)
    ease_after: Mapped[float] = mapped_column(Float, nullable=False)
    interval_after: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False, index=True
    )
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)

    word_id = synonym("phrase_id")


class Setting(Base):
    """Настройки приложения в виде key/value, чтобы менять их без миграций."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
