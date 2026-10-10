"""Словарь фраз: CRUD, метки, занятия, статистика и изоляция от слов.

Фразы — отдельная колода: свои таблицы, свои маршруты, свои лимиты. Каждый
блок проверяет и поведение фраз, и то, что слова при этом не задеты.
"""

import random
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.clock import utcnow
from app.config import settings
from app.exercises import word_key_for
from app.models import (
    ExerciseType,
    Label,
    Phrase,
    PhraseLabel,
    PhraseProgress,
    PhraseReviewLog,
    Progress,
    ReviewLog,
    Word,
    WordStatus,
)
from app.srs import EXERCISE_ROUNDS, SrsState, apply_answer

PHRASEBOOK = [
    ("break the ice", "растопить лёд"),
    ("It's up to you.", "Решать тебе."),
    ("look after", "присматривать"),
    ("once in a blue moon", "очень редко"),
    ("hit the sack", "лечь спать"),
    ("piece of cake", "проще простого"),
]


@pytest.fixture
def phrases(db_session: Session) -> list[Phrase]:
    now = utcnow()
    items = [
        Phrase(text=t, text_key=word_key_for(t), translation=tr, created_at=now)
        for t, tr in PHRASEBOOK
    ]
    db_session.add_all(items)
    db_session.commit()
    return items


# ----------------------------------------------------------------------- помощники


def _ok(response, code: int = 200) -> Any:
    assert response.status_code == code, response.text
    return response.json() if code != 204 else None


def _create(client: TestClient, text: str, translation: str, **extra) -> dict:
    return _ok(
        client.post("/api/phrases", json={"word": text, "translation": translation, **extra}),
        201,
    )


def _session(client: TestClient, mode: str, prefix: str = "/api/phrase-study") -> dict:
    return _ok(client.get(f"{prefix}/session", params={"mode": mode}))


def _select(client: TestClient, phrase_id: int, action: str = "learn", **extra) -> dict:
    return _ok(
        client.post(
            "/api/phrase-study/select",
            json={"word_id": phrase_id, "action": action, **extra},
        )
    )


def _start(client: TestClient, count: int = 5) -> tuple[str, list[int]]:
    body = _session(client, "learn")
    started = [p["id"] for p in body["new_words"]][:count]
    for phrase_id in started:
        _select(client, phrase_id)
    return body["session_id"], started


def _answers(items, ids) -> dict[int, dict[str, str]]:
    chosen = set(ids)
    return {
        item.id: {
            exercise: (
                item.translation if exercise == ExerciseType.CHOICE_EN_RU else item.word
            )
            for exercise in EXERCISE_ROUNDS
        }
        for item in items
        if item.id in chosen
    }


def _answer(client, prefix, item_id, exercise, answer, session_id, mode, attempt=1):
    return _ok(
        client.post(
            f"{prefix}/answer",
            json={
                "word_id": item_id,
                "exercise": exercise,
                "answer": answer,
                "session_id": session_id,
                "mode": mode,
                "attempt": attempt,
            },
        )
    )


def _play(
    client: TestClient,
    rounds: list[dict],
    answers: dict[int, dict[str, str]],
    session_id: str,
    mode: str,
    prefix: str = "/api/phrase-study",
    wrong_for: int | None = None,
) -> None:
    """Пройти все раунды верно; `wrong_for` ошибается в первом раунде и исправляется."""
    for index, round_ in enumerate(rounds):
        exercise = round_["exercise"]
        for card in round_["exercises"]:
            item_id = card["word_id"]
            attempt = 1
            if item_id == wrong_for and index == 0:
                _answer(client, prefix, item_id, exercise, "заведомо неверно", session_id, mode)
                attempt = 2
            _answer(
                client,
                prefix,
                item_id,
                exercise,
                answers[item_id][exercise],
                session_id,
                mode,
                attempt,
            )


def _finish(client, session_id, mode, prefix="/api/phrase-study") -> list[dict]:
    return _ok(client.post(f"{prefix}/finish", json={"session_id": session_id, "mode": mode}))


def _release(db_session: Session, model, ids: list[int], overdue_days: list[float]) -> None:
    """Выпустить записи в повторение со сроком в прошлом."""
    for item_id, days in zip(ids, overdue_days, strict=True):
        progress = db_session.get(model, item_id)
        progress.status = WordStatus.REVIEW
        progress.step = 4
        progress.repetitions = 1
        progress.interval_days = 1.0
        progress.due_at = utcnow() - timedelta(days=days)
    db_session.commit()


def _count(db_session: Session, model) -> int:
    return db_session.scalar(select(func.count()).select_from(model)) or 0


# ------------------------------------------------------------------- словарь (US1)


def test_created_phrase_is_listed_as_new(client: TestClient):
    created = _create(client, "break the ice", "растопить лёд")

    page = _ok(client.get("/api/phrases"))
    assert page["total"] == 1
    [item] = page["items"]
    assert item["id"] == created["id"]
    assert item["word"] == "break the ice"
    assert item["progress"] is None


def test_same_phrase_with_the_same_meaning_is_a_duplicate(client: TestClient):
    _create(client, "break the ice", "растопить лёд")

    response = client.post(
        "/api/phrases", json={"word": "Break  the ice", "translation": "растопить лёд"}
    )

    assert response.status_code == 409
    assert "Фраза" in response.json()["detail"]


def test_same_phrase_with_another_meaning_is_allowed(client: TestClient):
    _create(client, "break the ice", "растопить лёд")
    _create(client, "break the ice", "разрядить обстановку")

    assert _ok(client.get("/api/phrases"))["total"] == 2


def test_phrase_may_be_up_to_200_characters(client: TestClient):
    _create(client, "a" * 200, "длинная")

    response = client.post("/api/phrases", json={"word": "b" * 201, "translation": "длиннее"})
    assert response.status_code == 422


def test_editing_into_an_existing_pair_is_a_conflict(client: TestClient):
    _create(client, "break the ice", "растопить лёд")
    other = _create(client, "hit the sack", "лечь спать")

    response = client.patch(
        f"/api/phrases/{other['id']}",
        json={"word": "Break the ice", "translation": "растопить лёд"},
    )
    assert response.status_code == 409


def test_phrase_filters(client: TestClient, phrases: list[Phrase]):
    assert [p["word"] for p in _ok(client.get("/api/phrases?search=ice"))["items"]] == [
        "break the ice"
    ]

    _select(client, phrases[0].id)
    new = _ok(client.get("/api/phrases?status=new"))
    assert phrases[0].id not in {p["id"] for p in new["items"]}
    assert new["total"] == len(phrases) - 1

    _ok(client.put(f"/api/phrases/{phrases[2].id}/priority", json={"priority": True}))
    raised = _ok(client.get("/api/phrases?priority=true"))["items"]
    assert [p["id"] for p in raised] == [phrases[2].id]

    _ok(client.patch(f"/api/phrases/{phrases[1].id}", json={"labels": ["идиомы"]}))
    unlabeled = _ok(client.get("/api/phrases?label=none"))
    assert phrases[1].id not in {p["id"] for p in unlabeled["items"]}
    assert unlabeled["total"] == len(phrases) - 1


@pytest.mark.parametrize("target", ["learning", "review", "known", "suspended"])
def test_status_change_is_not_an_answer(
    client: TestClient, db_session: Session, phrases: list[Phrase], target: str
):
    phrase_id = phrases[0].id

    body = _ok(client.put(f"/api/phrases/{phrase_id}/status", json={"status": target}))
    assert body["progress"]["status"] == target

    body = _ok(client.put(f"/api/phrases/{phrase_id}/status", json={"status": "new"}))
    assert body["progress"] is None
    assert _count(db_session, PhraseReviewLog) == 0


def test_priority_needs_a_new_phrase(client: TestClient, phrases: list[Phrase]):
    _select(client, phrases[0].id)

    response = client.put(f"/api/phrases/{phrases[0].id}/priority", json={"priority": True})
    assert response.status_code == 409


def test_delete_phrase(client: TestClient, phrases: list[Phrase]):
    phrase_id = phrases[0].id

    _ok(client.delete(f"/api/phrases/{phrase_id}"), 204)

    response = client.get(f"/api/phrases/{phrase_id}")
    assert response.status_code == 404
    assert response.json()["detail"] == "Фраза не найдена"


# ------------------------------------------------------------- изоляция словарей


def test_phrase_is_absent_from_the_words(
    client: TestClient, words: list[Word], phrases: list[Phrase]
):
    assert _ok(client.get("/api/words?search=ice"))["total"] == 0
    assert _ok(client.get("/api/phrases?search=outsider"))["total"] == 0


def test_word_and_phrase_may_share_the_text(client: TestClient, db_session: Session):
    _ok(client.post("/api/words", json={"word": "look after", "translation": "присматривать"}), 201)
    _create(client, "look after", "присматривать")

    assert _ok(client.get("/api/words?search=look"))["total"] == 1
    assert _ok(client.get("/api/phrases?search=look"))["total"] == 1


# ------------------------------------------------------------------ метки фраз


def test_phrase_labels_are_separate_from_word_labels(client: TestClient, db_session: Session):
    created = _create(client, "break the ice", "растопить лёд", labels=["идиомы"])

    assert [label["name"] for label in created["labels"]] == ["идиомы"]
    assert _count(db_session, PhraseLabel) == 1
    assert _count(db_session, Label) == 0

    [label] = _ok(client.get("/api/phrase-labels"))
    assert label["name"] == "идиомы"
    assert label["word_count"] == 1
    assert _ok(client.get("/api/labels")) == []


def test_phrase_label_may_repeat_a_word_label_name(client: TestClient):
    _ok(client.post("/api/labels", json={"name": "кухня"}), 201)

    _ok(client.post("/api/phrase-labels", json={"name": "Кухня"}), 201)
    response = client.post("/api/phrase-labels", json={"name": "кухня"})
    assert response.status_code == 409


def test_phrase_label_rename_and_delete(client: TestClient, db_session: Session):
    word = {"word": "kettle", "translation": "чайник", "labels": ["быт"]}
    _ok(client.post("/api/words", json=word), 201)
    phrase = _create(client, "break the ice", "растопить лёд", labels=["быт"])
    [label] = _ok(client.get("/api/phrase-labels"))

    renamed = _ok(client.patch(f"/api/phrase-labels/{label['id']}", json={"name": "Быт"}))
    assert renamed["name"] == "Быт"
    assert renamed["word_count"] == 1

    _ok(client.delete(f"/api/phrase-labels/{label['id']}"), 204)
    assert _ok(client.get(f"/api/phrases/{phrase['id']}"))["labels"] == []
    # Метка слов с тем же названием не тронута
    [word_label] = _ok(client.get("/api/labels"))
    assert word_label["name"] == "быт"
    assert word_label["word_count"] == 1

    assert client.patch("/api/phrase-labels/999", json={"name": "x"}).status_code == 404


def test_phrases_filter_by_label(client: TestClient):
    tagged = _create(client, "break the ice", "растопить лёд", labels=["идиомы"])
    _create(client, "hit the sack", "лечь спать")
    [label] = _ok(client.get("/api/phrase-labels"))

    items = _ok(client.get(f"/api/phrases?label={label['id']}"))["items"]
    assert [p["id"] for p in items] == [tagged["id"]]


def test_phrase_labels_have_no_auto_labelling(client: TestClient):
    response = client.post("/api/phrase-labels/classify", json={"label_ids": [1]})
    assert response.status_code in (404, 405)


# ---------------------------------------------------------- учить фразы (US2)


def test_learn_session_offers_phrases_in_the_order_of_addition(
    client: TestClient, words: list[Word], phrases: list[Phrase]
):
    _ok(client.put("/api/settings", json={"new_words_order": "newest_first"}))
    _ok(client.put(f"/api/phrases/{phrases[4].id}/priority", json={"priority": True}))

    body = _session(client, "learn")
    offered = [p["id"] for p in body["new_words"]]
    assert offered == [phrases[4].id] + [p.id for p in phrases[:4]]
    assert body["session_id"]

    # Слова не получают фраз и по-прежнему слушают настройку порядка
    word_ids = [w["id"] for w in _session(client, "learn", "/api/study")["new_words"]]
    assert word_ids == [w.id for w in words[::-1][:5]]


def test_known_phrase_is_replaced_by_the_next_new_one(
    client: TestClient, phrases: list[Phrase]
):
    shown = [p["id"] for p in _session(client, "learn")["new_words"]]

    body = _select(client, shown[0], "know", exclude_ids=shown)
    assert body["replacement"]["id"] == phrases[5].id

    body = _select(client, shown[1], "know", exclude_ids=shown + [phrases[5].id])
    assert body["replacement"] is None


def test_learn_rounds_hold_only_phrases(
    client: TestClient, words: list[Word], phrases: list[Phrase]
):
    _, started = _start(client)

    rounds = _ok(client.post("/api/phrase-study/rounds", json={"word_ids": started}))

    assert [r["exercise"] for r in rounds] == list(EXERCISE_ROUNDS)
    texts = {p.word for p in phrases}
    translations = {p.translation for p in phrases}
    for round_ in rounds:
        assert {c["word_id"] for c in round_["exercises"]} == set(started)
        for card in round_["exercises"]:
            if round_["exercise"] == ExerciseType.CHOICE_RU_EN:
                assert set(card["options"]) <= texts
            elif round_["exercise"] == ExerciseType.CHOICE_EN_RU:
                assert set(card["options"]) <= translations


def test_learn_finish_releases_phrases(
    client: TestClient, db_session: Session, phrases: list[Phrase]
):
    session_id, started = _start(client)
    rounds = _ok(client.post("/api/phrase-study/rounds", json={"word_ids": started}))
    _play(client, rounds, _answers(phrases, started), session_id, "learn")

    results = _finish(client, session_id, "learn")

    assert {r["word_id"] for r in results} == set(started)
    for result in results:
        assert result["progress"]["status"] == WordStatus.REVIEW
        assert result["progress"]["interval_days"] == 1.0


def test_daily_limits_are_separate(
    client: TestClient,
    words: list[Word],
    phrases: list[Phrase],
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(settings, "daily_new_phrases_limit", 2)

    assert len(_session(client, "learn")["new_words"]) == 2
    assert len(_session(client, "learn", "/api/study")["new_words"]) == 5

    for phrase in phrases[:2]:
        _select(client, phrase.id)
    assert _session(client, "learn")["new_words"] == []

    monkeypatch.setattr(settings, "daily_new_limit", 1)
    client.post("/api/study/select", json={"word_id": words[0].id, "action": "learn"})
    assert _session(client, "learn", "/api/study")["new_words"] == []
    monkeypatch.setattr(settings, "daily_new_phrases_limit", 20)
    assert len(_session(client, "learn")["new_words"]) == 4


def test_empty_phrasebook_gives_an_empty_session(client: TestClient, words: list[Word]):
    body = _session(client, "learn")
    assert body["new_words"] == []
    assert body["session_id"] is None


def test_phrase_answers_go_to_the_phrase_log(
    client: TestClient, db_session: Session, words: list[Word], phrases: list[Phrase]
):
    session_id, started = _start(client, 1)
    rounds = _ok(client.post("/api/phrase-study/rounds", json={"word_ids": started}))
    _play(client, rounds, _answers(phrases, started), session_id, "learn")

    # Знакомство и пять ответов — всё в журнале фраз
    assert _count(db_session, PhraseReviewLog) == 1 + len(EXERCISE_ROUNDS)
    assert _count(db_session, ReviewLog) == 0

    # Чужой ключ занятия — пустой итог в обе стороны
    assert _finish(client, session_id, "learn", "/api/study") == []
    word_session = _session(client, "learn", "/api/study")["session_id"]
    assert _finish(client, word_session, "learn") == []


def test_word_and_phrase_ids_do_not_cross(
    client: TestClient, words: list[Word], phrases: list[Phrase]
):
    response = client.post(
        "/api/phrase-study/select", json={"word_id": 999, "action": "learn"}
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Фраза не найдена"


# ------------------------------------------------------- повторить фразы (US3)


def _due_decks(client, db_session, words, phrases) -> tuple[list[int], list[int]]:
    """Три фразы и три слова к повторению; фразы — с разной просрочкой."""
    _, phrase_ids = _start(client, 3)
    word_ids = [w["id"] for w in _session(client, "learn", "/api/study")["new_words"]][:3]
    for word_id in word_ids:
        client.post("/api/study/select", json={"word_id": word_id, "action": "learn"})
    _release(db_session, PhraseProgress, phrase_ids, [1, 3, 2])
    _release(db_session, Progress, word_ids, [1, 1, 1])
    return phrase_ids, word_ids


def test_review_session_takes_only_due_phrases(
    client: TestClient,
    db_session: Session,
    words: list[Word],
    phrases: list[Phrase],
    monkeypatch: pytest.MonkeyPatch,
):
    phrase_ids, _ = _due_decks(client, db_session, words, phrases)

    body = _session(client, "review")

    assert len(body["rounds"]) == len(EXERCISE_ROUNDS)
    for round_ in body["rounds"]:
        assert {c["word_id"] for c in round_["exercises"]} == set(phrase_ids)
    assert body["counts"]["review_due"] == 3

    # Самые просроченные первыми: внутри раунда порядок перемешан, поэтому
    # отбор виден, только когда в занятие помещаются не все
    monkeypatch.setattr(settings, "review_phrases_per_session", 2)
    body = _session(client, "review")
    assert {c["word_id"] for c in body["rounds"][0]["exercises"]} == {
        phrase_ids[1],
        phrase_ids[2],
    }


def test_review_finish_moves_phrases_like_words(
    client: TestClient, db_session: Session, words: list[Word], phrases: list[Phrase]
):
    phrase_ids, word_ids = _due_decks(client, db_session, words, phrases)
    db_session.expire_all()
    word_due = {w: db_session.get(Progress, w).due_at for w in word_ids}
    before = {
        p: SrsState(
            status=WordStatus.REVIEW,
            step=4,
            repetitions=1,
            ease=db_session.get(PhraseProgress, p).ease,
            interval_days=1.0,
            lapses=0,
            due_at=db_session.get(PhraseProgress, p).due_at,
        )
        for p in phrase_ids
    }

    body = _session(client, "review")
    stumbled = phrase_ids[0]
    _play(
        client,
        body["rounds"],
        _answers(phrases, phrase_ids),
        body["session_id"],
        "review",
        wrong_for=stumbled,
    )
    results = {r["word_id"]: r for r in _finish(client, body["session_id"], "review")}

    # SC-004: без ошибок — ровно тот же шаг SM-2, что у слова
    for phrase_id in phrase_ids[1:]:
        expected = apply_answer(before[phrase_id], quality=5, now=utcnow(), rng=random.Random(0))
        progress = results[phrase_id]["progress"]
        assert progress["status"] == WordStatus.REVIEW
        assert progress["repetitions"] == expected.repetitions
        assert progress["interval_days"] == expected.interval_days
        assert progress["ease"] == pytest.approx(expected.ease)

    # Ошибка — фраза забыта
    assert results[stumbled]["progress"]["status"] == WordStatus.LEARNING
    assert results[stumbled]["progress"]["lapses"] == 1
    db_session.expire_all()
    assert db_session.get(PhraseProgress, stumbled).due_at <= utcnow()

    # Повторный `finish` ничего не меняет
    assert _finish(client, body["session_id"], "review") == []

    # Слова не тронуты
    db_session.expire_all()
    assert {w: db_session.get(Progress, w).due_at for w in word_ids} == word_due


def test_unfinished_review_changes_nothing(
    client: TestClient, db_session: Session, words: list[Word], phrases: list[Phrase]
):
    phrase_ids, _ = _due_decks(client, db_session, words, phrases)
    db_session.expire_all()
    snapshot = {p: db_session.get(PhraseProgress, p).due_at for p in phrase_ids}

    body = _session(client, "review")
    _play(
        client, body["rounds"][:2], _answers(phrases, phrase_ids), body["session_id"], "review"
    )

    assert _finish(client, body["session_id"], "review") == []
    db_session.expire_all()
    assert {p: db_session.get(PhraseProgress, p).due_at for p in phrase_ids} == snapshot


# ------------------------------------------------------------ статистика (US5)


def test_stats_are_counted_per_deck(
    client: TestClient, db_session: Session, words: list[Word], phrases: list[Phrase]
):
    word_overview = _ok(client.get("/api/stats/overview"))
    word_daily = _ok(client.get("/api/stats/daily", params={"days": 7}))

    session_id, started = _start(client, 2)
    rounds = _ok(client.post("/api/phrase-study/rounds", json={"word_ids": started}))
    _play(client, rounds, _answers(phrases, started), session_id, "learn")

    # Статистика слов не заметила фраз
    assert _ok(client.get("/api/stats/overview")) == word_overview
    assert _ok(client.get("/api/stats/daily", params={"days": 7})) == word_daily

    overview = _ok(client.get("/api/phrase-stats/overview"))
    assert overview["total_words"] == len(phrases)
    assert overview["new"] == len(phrases) - 2
    assert overview["learning"] == 2
    assert overview["answers_today"] == 2 + 2 * len(EXERCISE_ROUNDS)
    assert overview["new_today"] == 2
    assert overview["streak_days"] == 1

    [today] = _ok(client.get("/api/phrase-stats/daily", params={"days": 1}))
    assert today["answers"] == 2 + 2 * len(EXERCISE_ROUNDS)
    assert today["new_words"] == 2

    # Ответ по слову не попадает в статистику фраз
    client.post("/api/study/select", json={"word_id": words[0].id, "action": "learn"})
    assert _ok(client.get("/api/phrase-stats/overview")) == overview
