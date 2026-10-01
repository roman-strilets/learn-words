"""Классификатор меток: языковая модель выбирает слову метку из набора.

Классифицировать тысячи слов по произвольным меткам пользователя без модели
нельзя, поэтому разметка спрашивает внешний сервис (по умолчанию локальную
Ollama) через `typesafe-sdk`. На каждое слово — вопрос `Choice`: критерии —
метки набора и явный вариант «ни одна». Все слова пачки уходят одним запросом.

Вызов изолирован здесь за протоколом `Classifier`: сервис разметки зависит
только от него, а тесты подменяют зависимость `get_classifier` фейком и не
ходят в сеть. Сам адаптер проверяется с `httpx2.MockTransport`.

Вопрос строится и ответ разбирается чистыми функциями `build_questions` и
`parse_choices` — их поведение закреплено табличными тестами.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

import httpx2
from fastapi import Depends
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from typesafe_sdk import (
    Choice,
    RetryPolicy,
    TypeSafeAPIConnectionError,
    TypeSafeAPIError,
    TypeSafeAPIResponseValidationError,
    TypeSafeAPITimeoutError,
    TypeSafeAuthenticationError,
    TypeSafeClient,
    TypeSafeError,
    TypeSafeNotFoundError,
    TypeSafePermissionDeniedError,
)

from app.config import settings
from app.db import get_session
from app.models import Setting

# --------------------------------------------------------------------- вопрос


@dataclass(frozen=True)
class WordItem:
    """Слово пачки. Перевод различает значения: `bark` — «кора» или «лаять»."""

    id: int
    word: str
    translation: str


@dataclass(frozen=True)
class LabelItem:
    id: int
    name: str
    description: str | None


@dataclass(frozen=True)
class ClassifierConfig:
    base_url: str
    api_key: str
    model: str


# Без явного варианта «ни одна» `Choice` обязан выбрать хоть что-то, и
# `bicycle` получил бы «кухню»
NONE_CHOICE = "none of the above"

INSTRUCTIONS = (
    'Which category does the English word "{word}" (Russian translation: "{translation}") '
    'belong to? Choose "{none}" if none of the categories fits.'
)


def none_key(labels: Sequence[LabelItem]) -> str:
    """Ключ варианта «ни одна», не совпадающий ни с одной меткой без учёта регистра.

    Метку могут так и назвать — тогда ответ «ни одна» поставил бы её.
    """
    taken = {label.name.casefold() for label in labels}
    key, n = NONE_CHOICE, 1
    while key.casefold() in taken:
        n += 1
        key = f"{NONE_CHOICE} ({n})"
    return key


def build_questions(
    words: Sequence[WordItem], labels: Sequence[LabelItem]
) -> dict[str, Choice]:
    """По вопросу на запись. Ключ — id: у слова бывает несколько значений.

    Критерий метки — её описание, если оно есть, иначе название.
    """
    none = none_key(labels)
    criteria: dict[str, str] = {label.name: label.description or label.name for label in labels}
    criteria[none] = "None of the above"
    return {
        str(word.id): Choice(
            instructions=INSTRUCTIONS.format(
                word=word.word, translation=word.translation, none=none
            ),
            criteria=criteria,
        )
        for word in words
    }


def parse_choices(
    choices: Mapping[str, str], words: Sequence[WordItem], labels: Sequence[LabelItem]
) -> dict[int, int | None]:
    """Ответы модели `{ключ вопроса: выбранный критерий}` → `{id слова: id метки | None}`.

    «Ни одна», нет ответа и ответ вне набора — `None`: SDK не проверяет, что
    выбор взят из критериев.
    """
    by_name = {label.name: label.id for label in labels}
    return {word.id: by_name.get(choices.get(str(word.id), "")) for word in words}


# ---------------------------------------------------------------------- ошибки


class ClassifierError(Exception):
    """Классификатор недоступен или ответил ошибкой.

    502 — сервис ответил ошибкой или недоступен, 504 — не ответил вовремя:
    виноват не запрос пользователя, поэтому не 4xx.
    """

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def translate_error(exc: TypeSafeError, config: ClassifierConfig) -> ClassifierError:
    """Исключение SDK → понятная причина. Порядок — от частного к общему:
    таймаут — подкласс ошибки соединения, ошибка схемы — подкласс ошибки API.
    """
    if isinstance(exc, TypeSafeAPITimeoutError):
        return ClassifierError(504, f"Модель не ответила за {_seconds(exc.timeout)} с")
    if isinstance(exc, TypeSafeAPIConnectionError):
        return ClassifierError(502, f"Сервис разметки недоступен по адресу {config.base_url}")
    if isinstance(exc, TypeSafeNotFoundError):
        return ClassifierError(502, f"Модель «{config.model}» не найдена")
    if isinstance(exc, TypeSafeAuthenticationError | TypeSafePermissionDeniedError):
        return ClassifierError(502, "Сервис отклонил ключ доступа")
    if isinstance(exc, TypeSafeAPIResponseValidationError):
        return ClassifierError(502, "Сервис ответил не по схеме")
    if isinstance(exc, TypeSafeAPIError):
        return ClassifierError(502, f"Сервис разметки ответил ошибкой {exc.status}")
    return ClassifierError(502, f"Неверные настройки классификатора: {exc}")


def _seconds(timeout: float | httpx2.Timeout) -> str:
    if isinstance(timeout, httpx2.Timeout):
        timeout = timeout.read or 0
    return f"{timeout:g}"


# ---------------------------------------------------------------------- адаптер


class Classifier(Protocol):
    def classify(
        self, words: list[WordItem], labels: list[LabelItem]
    ) -> dict[int, int | None]: ...

    def check(self) -> None: ...


# Две минуты ожидания с повторами SDK по умолчанию превратились бы в шесть,
# а пользователь всё это время смотрел бы на застывший прогресс
NO_RETRY = RetryPolicy(max_retries=0)


class TypeSafeClassifier:
    """Классификатор поверх `typesafe-sdk`.

    Адрес, ключ и модель передаются явно, поэтому переменные окружения
    `TYPESAFE_*` их не перебивают. `transport` — для тестов.
    """

    def __init__(
        self,
        config: ClassifierConfig,
        timeout: float,
        transport: httpx2.BaseTransport | None = None,
    ) -> None:
        self._config = config
        self._timeout = timeout
        self._transport = transport

    def classify(
        self, words: list[WordItem], labels: list[LabelItem]
    ) -> dict[int, int | None]:
        state = {"words": [{"word": w.word, "translation": w.translation} for w in words]}
        try:
            with self._client() as client:
                response = client.system_one(
                    state=state, questions=build_questions(words, labels)
                )
        except TypeSafeError as exc:
            err = translate_error(exc, self._config)
            if err.status_code == 504:
                err.detail += " — уменьшите пачку"
            raise err from exc
        answers = {key: answer.choice for key, answer in response.choices.items()}
        return parse_choices(answers, words, labels)

    def check(self) -> None:
        """Один крошечный вопрос — проверяет адрес, ключ, модель и сам маршрут разом.

        `models.list()` не годится: Ollama отвечает на него в формате OpenAI.
        """
        try:
            with self._client() as client:
                client.system_one(
                    state="apple",
                    questions={
                        "check": Choice(
                            instructions="Is this a fruit or a tool?",
                            criteria={"fruit": None, "tool": None},
                        )
                    },
                )
        except TypeSafeError as exc:
            raise translate_error(exc, self._config) from exc

    def _client(self) -> TypeSafeClient:
        return TypeSafeClient(
            base_url=self._config.base_url,
            api_key=self._config.api_key,
            model=self._config.model,
            timeout=self._timeout,
            retry=NO_RETRY,
            transport=self._transport,
        )


# --------------------------------------------------------------------- настройки

# Ключи в таблице `settings`. Строки нет — действует значение из `app/config.py`
CLASSIFIER_BASE_URL_KEY = "classifier_base_url"
CLASSIFIER_API_KEY_KEY = "classifier_api_key"
CLASSIFIER_MODEL_KEY = "classifier_model"
_KEYS = (CLASSIFIER_BASE_URL_KEY, CLASSIFIER_API_KEY_KEY, CLASSIFIER_MODEL_KEY)


def load_classifier_config(session: Session) -> tuple[ClassifierConfig, bool]:
    """Действующие адрес, ключ и модель и признак «всё по умолчанию»."""
    rows = {
        row.key: row.value for row in session.scalars(select(Setting).where(Setting.key.in_(_KEYS)))
    }
    config = ClassifierConfig(
        base_url=rows.get(CLASSIFIER_BASE_URL_KEY, settings.classifier_base_url),
        api_key=rows.get(CLASSIFIER_API_KEY_KEY, settings.classifier_api_key),
        model=rows.get(CLASSIFIER_MODEL_KEY, settings.classifier_model),
    )
    return config, not rows


def save_classifier_config(session: Session, config: ClassifierConfig) -> None:
    """Сохранить три значения разом: адрес от одного сервиса и модель от другого не
    должны оказаться вместе. Транзакция — запроса, коммитит `get_session`.
    """
    values = {
        CLASSIFIER_BASE_URL_KEY: config.base_url,
        CLASSIFIER_API_KEY_KEY: config.api_key,
        CLASSIFIER_MODEL_KEY: config.model,
    }
    for key, value in values.items():
        session.merge(Setting(key=key, value=value))
    session.flush()


def reset_classifier_config(session: Session) -> None:
    """Вернуть значения по умолчанию.

    Строки удаляются, а не перезаписываются значениями из `config.py`: тогда
    смена умолчаний в конфиге доходит до пользователя, который ничего не менял.
    """
    session.execute(delete(Setting).where(Setting.key.in_(_KEYS)))
    session.flush()


# ------------------------------------------------------------- зависимости API

ClassifierFactory = Callable[[ClassifierConfig, float], Classifier]


def get_classifier_factory() -> ClassifierFactory:
    """Как построить классификатор по настройкам. Тесты подменяют фабрику."""
    return TypeSafeClassifier


def get_classifier(
    session: Session = Depends(get_session),
    factory: ClassifierFactory = Depends(get_classifier_factory),
) -> Classifier:
    """Классификатор с сохранёнными настройками и таймаутом пачки."""
    config, _ = load_classifier_config(session)
    return factory(config, settings.classifier_timeout_seconds)
