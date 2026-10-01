"""Классификатор меток без сети: вопрос, разбор ответа и адаптер к SDK."""

import json

import httpx2
import pytest

from app.classifier import (
    NONE_CHOICE,
    ClassifierConfig,
    ClassifierError,
    LabelItem,
    TypeSafeClassifier,
    WordItem,
    build_questions,
    parse_choices,
)

KITCHEN = LabelItem(id=10, name="кухня", description=None)
BODY = LabelItem(id=11, name="тело", description="parts of the human body")
LABELS = [KITCHEN, BODY]

SPOON = WordItem(id=1, word="spoon", translation="ложка")
ELBOW = WordItem(id=2, word="elbow", translation="локоть")
BARK_TREE = WordItem(id=3, word="bark", translation="кора")
BARK_DOG = WordItem(id=4, word="bark", translation="лаять")

CONFIG = ClassifierConfig(base_url="http://models.test:11434", api_key="secret", model="nimble")


# --------------------------------------------------------------- build_questions


def test_question_per_record_keyed_by_id():
    questions = build_questions([SPOON, BARK_TREE, BARK_DOG], LABELS)

    # Два значения одного слова — два вопроса
    assert list(questions) == ["1", "3", "4"]
    assert '"spoon"' in questions["1"].instructions
    assert '"ложка"' in questions["1"].instructions
    assert '"кора"' in questions["3"].instructions
    assert '"лаять"' in questions["4"].instructions


def test_criteria_are_labels_and_none():
    criteria = build_questions([SPOON], LABELS)["1"].criteria

    # Описание — критерий вместо названия, у метки без описания — название
    assert criteria == {
        "кухня": "кухня",
        "тело": "parts of the human body",
        NONE_CHOICE: "None of the above",
    }


@pytest.mark.parametrize(
    ("names", "expected"),
    [
        (["кухня"], NONE_CHOICE),
        (["None of the above"], f"{NONE_CHOICE} (2)"),
        (["none of the above", f"{NONE_CHOICE} (2)"], f"{NONE_CHOICE} (3)"),
    ],
)
def test_none_key_avoids_a_label_name(names: list[str], expected: str):
    labels = [LabelItem(id=i, name=name, description=None) for i, name in enumerate(names)]

    question = build_questions([SPOON], labels)["1"]

    assert expected in question.criteria
    assert f'"{expected}"' in question.instructions
    assert len(question.criteria) == len(labels) + 1


# ----------------------------------------------------------------- parse_choices


@pytest.mark.parametrize(
    ("choice", "expected"),
    [
        ("кухня", KITCHEN.id),
        ("тело", BODY.id),
        (NONE_CHOICE, None),
        ("растения", None),  # вне набора
        ("Кухня", None),  # точное совпадение, как ключ критерия
    ],
)
def test_choice_maps_to_label(choice: str, expected: int | None):
    assert parse_choices({"1": choice}, [SPOON], LABELS) == {SPOON.id: expected}


def test_missing_answer_is_no_label():
    assert parse_choices({"1": "кухня"}, [SPOON, ELBOW], LABELS) == {
        SPOON.id: KITCHEN.id,
        ELBOW.id: None,
    }


# ---------------------------------------------------------------------- адаптер


def _answer(choice: str) -> dict:
    return {"type": "choice", "choice": choice, "confidence": 0.9, "probabilities": {choice: 0.9}}


def _ok(answers: dict) -> httpx2.Response:
    usage = {"input_tokens": 10, "output_tokens": 2}
    return httpx2.Response(200, json={"model": "nimble", "usage": usage, "answers": answers})


class Recorder:
    """Обработчик `MockTransport`: запоминает запросы и отвечает заданным."""

    def __init__(self, reply):
        self.reply = reply
        self.requests: list[httpx2.Request] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply(request) if callable(self.reply) else self.reply


def _classifier(handler: Recorder) -> TypeSafeClassifier:
    return TypeSafeClassifier(CONFIG, timeout=5.0, transport=httpx2.MockTransport(handler))


def test_adapter_sends_one_request_and_parses_answers():
    handler = Recorder(_ok({"1": _answer("кухня"), "2": _answer(NONE_CHOICE)}))

    result = _classifier(handler).classify([SPOON, ELBOW], LABELS)

    assert result == {SPOON.id: KITCHEN.id, ELBOW.id: None}
    [request] = handler.requests
    assert request.method == "POST"
    assert str(request.url) == "http://models.test:11434/v1/systemone"
    assert request.headers["Authorization"] == "Bearer secret"
    body = json.loads(request.content)
    assert body["model"] == "nimble"
    assert set(body["questions"]) == {"1", "2"}
    assert NONE_CHOICE in body["questions"]["1"]["criteria"]
    assert body["state"] == {
        "words": [
            {"word": "spoon", "translation": "ложка"},
            {"word": "elbow", "translation": "локоть"},
        ]
    }


def test_adapter_ignores_typesafe_environment(monkeypatch):
    monkeypatch.setenv("TYPESAFE_BASE_URL", "http://elsewhere.test")
    monkeypatch.setenv("TYPESAFE_DEFAULT_MODEL", "other")
    monkeypatch.setenv("TYPESAFE_API_KEY", "other")
    handler = Recorder(_ok({"1": _answer("кухня")}))

    _classifier(handler).classify([SPOON], LABELS)

    [request] = handler.requests
    assert request.url.host == "models.test"
    assert request.headers["Authorization"] == "Bearer secret"
    assert json.loads(request.content)["model"] == "nimble"


def test_check_asks_one_question():
    handler = Recorder(_ok({"check": _answer("fruit")}))

    _classifier(handler).check()

    [request] = handler.requests
    assert len(json.loads(request.content)["questions"]) == 1


@pytest.mark.parametrize(
    ("reply", "status_code", "detail"),
    [
        (
            httpx2.Response(404, json={"error": "model 'nimble' not found"}),
            502,
            "Модель «nimble» не найдена",
        ),
        (httpx2.Response(401, json={"error": "bad key"}), 502, "Сервис отклонил ключ доступа"),
        (httpx2.Response(403, json={"error": "denied"}), 502, "Сервис отклонил ключ доступа"),
        (httpx2.Response(500, text="boom"), 502, "Сервис разметки ответил ошибкой 500"),
        (httpx2.Response(200, json={"oops": True}), 502, "Сервис ответил не по схеме"),
        (
            httpx2.ConnectError("refused"),
            502,
            "Сервис разметки недоступен по адресу http://models.test:11434",
        ),
        (httpx2.ReadTimeout("slow"), 504, "Модель не ответила за 5 с — уменьшите пачку"),
    ],
)
def test_adapter_translates_failures_without_retries(reply, status_code: int, detail: str):
    handler = Recorder(reply)

    with pytest.raises(ClassifierError) as caught:
        _classifier(handler).classify([SPOON], LABELS)

    assert caught.value.status_code == status_code
    assert caught.value.detail == detail
    # Повторов нет: ни на 5xx, ни на обрыв, ни на таймаут
    assert len(handler.requests) == 1


def test_check_reports_the_same_failure():
    handler = Recorder(httpx2.Response(404, json={"error": "not found"}))

    with pytest.raises(ClassifierError) as caught:
        _classifier(handler).check()

    assert caught.value.detail == "Модель «nimble» не найдена"


def test_bad_key_is_a_failure_not_a_crash():
    classifier = TypeSafeClassifier(
        ClassifierConfig(base_url=CONFIG.base_url, api_key="with space", model="nimble"),
        timeout=5.0,
        transport=httpx2.MockTransport(Recorder(_ok({}))),
    )

    with pytest.raises(ClassifierError) as caught:
        classifier.check()

    assert caught.value.status_code == 502
