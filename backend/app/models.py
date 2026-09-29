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
from sqlalchemy.orm import Mapped, mapped_column, relationship

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
    """

    __tablename__ = "labels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    name_key: Mapped[str] = mapped_column(String(50), nullable=False)
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


class Setting(Base):
    """Настройки приложения в виде key/value, чтобы менять их без миграций."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
