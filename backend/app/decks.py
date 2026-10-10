"""Колоды: слова и фразы.

Алгоритм занятия один — раунды, оценка в `finish`, дистракторы, фильтры
словаря и метки. Чтобы не держать две его копии, общий код получает описание
колоды и через него находит свои таблицы, параметры занятия и тексты ошибок
(research R2). Поля моделей фраз, которые читает общий код, названы как у слов
синонимами (`Phrase.word`, `PhraseProgress.word_id` …), поэтому код пишет
`deck.item.word_key` и работает для обеих колод.

Параметры занятия читаются из `settings` при каждом обращении, а не
копируются при импорте: тесты и `.env` меняют их на живом объекте.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import Table

from app.config import settings
from app.models import (
    Label,
    Phrase,
    PhraseLabel,
    PhraseProgress,
    PhraseReviewLog,
    Progress,
    ReviewLog,
    Word,
    phrase_label_links,
    word_labels,
)


@dataclass(frozen=True)
class Deck:
    name: str
    item: type[Word] | type[Phrase]
    progress: type[Progress] | type[PhraseProgress]
    log: type[ReviewLog] | type[PhraseReviewLog]
    label: type[Label] | type[PhraseLabel]
    # Связка «запись — метка»; первая колонка — id записи, вторая — `label_id`
    links: Table
    _new_per_session: Callable[[], int]
    _review_per_session: Callable[[], int]
    _daily_new_limit: Callable[[], int]
    # Порядок новых из настройки `new_words_order`; без неё — по добавлению
    uses_order_setting: bool
    # Апостроф при проверке ответа не важен: «It's» = «Its» (research R4)
    drop_apostrophes: bool
    not_found: str
    label_not_found: str
    # «Слово «…» с переводом «…» уже есть в словаре»
    duplicate_detail: Callable[[str, str], str]

    @property
    def new_per_session(self) -> int:
        return self._new_per_session()

    @property
    def review_per_session(self) -> int:
        return self._review_per_session()

    @property
    def daily_new_limit(self) -> int:
        return self._daily_new_limit()

    @property
    def link_item_id(self):
        """Колонка связки с id записи: `word_id` или `phrase_id`."""
        return self.links.c[0]


WORDS = Deck(
    name="words",
    item=Word,
    progress=Progress,
    log=ReviewLog,
    label=Label,
    links=word_labels,
    _new_per_session=lambda: settings.new_words_per_session,
    _review_per_session=lambda: settings.review_words_per_session,
    _daily_new_limit=lambda: settings.daily_new_limit,
    uses_order_setting=True,
    drop_apostrophes=False,
    not_found="Слово не найдено",
    label_not_found="Метка не найдена",
    duplicate_detail=lambda word, translation: (
        f"Слово «{word}» с переводом «{translation}» уже есть в словаре"
    ),
)

PHRASES = Deck(
    name="phrases",
    item=Phrase,
    progress=PhraseProgress,
    log=PhraseReviewLog,
    label=PhraseLabel,
    links=phrase_label_links,
    _new_per_session=lambda: settings.new_phrases_per_session,
    _review_per_session=lambda: settings.review_phrases_per_session,
    _daily_new_limit=lambda: settings.daily_new_phrases_limit,
    uses_order_setting=False,
    drop_apostrophes=True,
    not_found="Фраза не найдена",
    label_not_found="Метка не найдена",
    duplicate_detail=lambda phrase, translation: (
        f"Фраза «{phrase}» с переводом «{translation}» уже есть в словаре"
    ),
)
