"""Занятие по группе: маршруты `/api/group-study`, круг по метке и изоляция
от основного обучения.

Каждый блок проверяет и само занятие, и то, что прогресс, журнал, статистика
и обычные занятия при этом не задеты.
"""

from collections.abc import Collection
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.clock import utcnow
from app.config import settings
from app.models import (
    ExerciseType,
    GroupCycleWord,
    GroupReviewLog,
    Progress,
    ReviewLog,
    Word,
)
from app.srs import EXERCISE_ROUNDS

# ----------------------------------------------------------------------- помощники


def _ok(response, code: int = 200) -> Any:
    assert response.status_code == code, response.text
    return response.json() if code != 204 else None


def _label(client: TestClient, name: str, word_ids: list[int]) -> int:
    """Завести метку и поставить её словам, не снимая их прежних меток."""
    label_id = _ok(client.post("/api/labels", json={"name": name}), 201)["id"]
    for word_id in word_ids:
        _tag(client, word_id, name)
    return label_id


def _tag(client: TestClient, word_id: int, name: str) -> None:
    current = [lbl["name"] for lbl in _ok(client.get(f"/api/words/{word_id}"))["labels"]]
    _ok(client.patch(f"/api/words/{word_id}", json={"labels": [*current, name]}))


def _untag(client: TestClient, word_id: int, name: str) -> None:
    current = [lbl["name"] for lbl in _ok(client.get(f"/api/words/{word_id}"))["labels"]]
    _ok(
        client.patch(
            f"/api/words/{word_id}", json={"labels": [n for n in current if n != name]}
        )
    )


def _session(client: TestClient, label_id: int) -> dict:
    return _ok(client.post("/api/group-study/session", json={"label_id": label_id}))


def _groups(client: TestClient) -> dict[int, dict]:
    return {g["label_id"]: g for g in _ok(client.get("/api/group-study/groups"))}


def _answer_raw(client, label_id, session_id, word_id, exercise, answer, attempt=1):
    return client.post(
        "/api/group-study/answer",
        json={
            "word_id": word_id,
            "label_id": label_id,
            "session_id": session_id,
            "exercise": exercise,
            "answer": answer,
            "attempt": attempt,
        },
    )


def _answer(client, label_id, session_id, word_id, exercise, answer, attempt=1) -> dict:
    return _ok(_answer_raw(client, label_id, session_id, word_id, exercise, answer, attempt))


def _right(word: Word, exercise: str) -> str:
    return word.translation if exercise == ExerciseType.CHOICE_EN_RU else word.word


def _play(
    client: TestClient,
    db_session: Session,
    body: dict,
    wrong_for: Collection[int] = frozenset(),
) -> None:
    """Пройти все раунды порции верно; слова из `wrong_for` сначала ошибаются."""
    for round_ in body["rounds"]:
        exercise = round_["exercise"]
        for card in round_["exercises"]:
            word = db_session.get(Word, card["word_id"])
            attempt = 1
            if word.id in wrong_for:
                _answer(
                    client, body["label_id"], body["session_id"], word.id, exercise, "мимо"
                )
                attempt = 2
            _answer(
                client,
                body["label_id"],
                body["session_id"],
                word.id,
                exercise,
                _right(word, exercise),
                attempt,
            )


def _finish(client: TestClient, session_id: str) -> list[dict]:
    return _ok(client.post("/api/group-study/finish", json={"session_id": session_id}))


def _portion(body: dict) -> list[int]:
    return [card["word_id"] for card in body["rounds"][0]["exercises"]] if body["rounds"] else []


def _study(client, db_session, label_id, wrong_for=frozenset()) -> tuple[dict, list[dict]]:
    body = _session(client, label_id)
    _play(client, db_session, body, wrong_for)
    return body, _finish(client, body["session_id"])


def _count(db_session: Session, model) -> int:
    return db_session.scalar(select(func.count()).select_from(model)) or 0


# ------------------------------------------------------------------ занятие (US1)


def test_groups_list_word_labels_alphabetically(client: TestClient, words: list[Word]):
    kitchen = _label(client, "кухня", [w.id for w in words[:3]])
    airport = _label(client, "Аэропорт", [])
    _ok(client.put(f"/api/words/{words[0].id}/status", json={"status": "known"}))
    _ok(client.post("/api/phrase-labels", json={"name": "Бытовые фразы"}), 201)

    groups = _ok(client.get("/api/group-study/groups"))
    assert groups == [
        {"label_id": airport, "name": "Аэропорт", "word_count": 0, "done": 0, "cycle": 0},
        {"label_id": kitchen, "name": "кухня", "word_count": 3, "done": 0, "cycle": 0},
    ]


def test_session_gives_five_rounds_of_the_label_words(client: TestClient, words: list[Word]):
    member_ids = {w.id for w in words[:3]}
    label_id = _label(client, "кухня", sorted(member_ids))

    body = _session(client, label_id)
    assert body["session_id"]
    assert "new_words" not in body
    assert [r["exercise"] for r in body["rounds"]] == list(EXERCISE_ROUNDS)
    for round_ in body["rounds"]:
        assert {card["word_id"] for card in round_["exercises"]} == member_ids
        assert len(round_["exercises"]) == 3
        assert all(card["type"] != "intro" for card in round_["exercises"])
    assert (body["word_count"], body["done"], body["cycle"]) == (3, 0, 1)


def test_big_label_gives_a_portion(client: TestClient, words: list[Word]):
    label_id = _label(client, "всё", [w.id for w in words])
    body = _session(client, label_id)
    for round_ in body["rounds"]:
        assert len(round_["exercises"]) == settings.group_words_per_session == 5


def test_label_without_words_has_no_session(client: TestClient, db_session: Session):
    label_id = _label(client, "пусто", [])
    body = _session(client, label_id)
    assert body["session_id"] is None
    assert body["rounds"] == []
    assert _count(db_session, GroupCycleWord) == 0


def test_unknown_label_is_404(client: TestClient):
    response = client.post("/api/group-study/session", json={"label_id": 999})
    assert response.status_code == 404
    assert response.json()["detail"] == "Метка не найдена"


def test_new_word_is_answered_without_progress(
    client: TestClient, db_session: Session, words: list[Word]
):
    word = words[0]
    label_id = _label(client, "кухня", [word.id])
    body = _session(client, label_id)

    right = _answer(client, label_id, body["session_id"], word.id, "letters", word.word)
    assert right["correct"] is True
    assert right["repeat_in_session"] is False
    assert "progress" not in right

    wrong = _answer(client, label_id, body["session_id"], word.id, "choice_ru_en", "мимо")
    assert wrong["correct"] is False
    assert wrong["repeat_in_session"] is True
    assert wrong["next_exercise"]["type"] == "choice_ru_en"
    assert wrong["correct_answer"] == word.word

    assert db_session.get(Progress, word.id) is None


def test_answer_errors(client: TestClient, words: list[Word]):
    label_id = _label(client, "кухня", [words[0].id])
    session_id = _session(client, label_id)["session_id"]

    intro = _answer_raw(client, label_id, session_id, words[0].id, "intro", "learn")
    assert intro.status_code == 422

    stranger = _answer_raw(client, label_id, session_id, words[1].id, "letters", "x")
    assert stranger.status_code == 409
    assert stranger.json()["detail"] == "Слова больше нет в группе"

    unknown = _answer_raw(client, label_id, session_id, 999, "letters", "x")
    assert unknown.status_code == 404
    assert unknown.json()["detail"] == "Слово не найдено"

    no_label = _answer_raw(client, 999, session_id, words[0].id, "letters", "x")
    assert no_label.status_code == 404


def test_every_answer_is_logged_in_group_log(
    client: TestClient, db_session: Session, words: list[Word]
):
    label_id = _label(client, "кухня", [w.id for w in words[:2]])
    body = _session(client, label_id)
    _play(client, db_session, body, wrong_for={words[0].id})

    logs = db_session.scalars(select(GroupReviewLog)).all()
    # 2 слова × 5 раундов + по ошибке в каждом раунде у первого слова
    assert len(logs) == 2 * 5 + 5
    assert {log.label_id for log in logs} == {label_id}
    assert {log.session_id for log in logs} == {body["session_id"]}
    assert _count(db_session, ReviewLog) == 0


def test_finish_marks_words_done(client: TestClient, db_session: Session, words: list[Word]):
    ids = [w.id for w in words[:3]]
    label_id = _label(client, "кухня", ids)
    body = _session(client, label_id)
    _play(client, db_session, body, wrong_for={ids[0]})

    results = _finish(client, body["session_id"])
    assert sorted(results, key=lambda r: r["word_id"]) == [
        {"word_id": ids[0], "mistakes": 5},
        {"word_id": ids[1], "mistakes": 0},
        {"word_id": ids[2], "mistakes": 0},
    ]
    group = _groups(client)[label_id]
    assert (group["word_count"], group["done"], group["cycle"]) == (3, 3, 1)


def test_unfinished_word_is_not_marked(
    client: TestClient, db_session: Session, words: list[Word]
):
    ids = [w.id for w in words[:2]]
    label_id = _label(client, "кухня", ids)
    body = _session(client, label_id)
    # Первое слово проходит всё, второе — только первый раунд
    for round_ in body["rounds"]:
        for card in round_["exercises"]:
            if card["word_id"] == ids[1] and round_["exercise"] != "choice_ru_en":
                continue
            word = db_session.get(Word, card["word_id"])
            _answer(
                client,
                label_id,
                body["session_id"],
                word.id,
                round_["exercise"],
                _right(word, round_["exercise"]),
            )

    assert [r["word_id"] for r in _finish(client, body["session_id"])] == [ids[0]]
    assert _groups(client)[label_id]["done"] == 1


def test_unknown_session_finishes_empty(client: TestClient):
    assert _finish(client, "no-such-session") == []


def test_choice_options_come_from_whole_dictionary(client: TestClient, words: list[Word]):
    members = words[:3]
    label_id = _label(client, "кухня", [w.id for w in members])
    body = _session(client, label_id)

    member_words = {w.word for w in members}
    member_translations = {w.translation for w in members}
    by_type = {r["exercise"]: r["exercises"] for r in body["rounds"]}
    for card in by_type["choice_ru_en"]:
        assert set(card["options"]) - member_words
    for card in by_type["choice_en_ru"]:
        assert set(card["options"]) - member_translations


# ------------------------------------------------------------- изоляция (US2)


def _snapshot(client: TestClient, db_session: Session) -> dict:
    db_session.expire_all()
    learn = _ok(client.get("/api/study/session", params={"mode": "learn"}))
    review = _ok(client.get("/api/study/session", params={"mode": "review"}))
    return {
        "progress": db_session.execute(text("SELECT * FROM progress ORDER BY word_id")).all(),
        "priority": db_session.execute(text("SELECT id, priority FROM words ORDER BY id")).all(),
        "review_log": _count(db_session, ReviewLog),
        "overview": _ok(client.get("/api/stats/overview")),
        "daily": _ok(client.get("/api/stats/daily")),
        "learn": [w["id"] for w in learn["new_words"]],
        "review": sorted(
            {card["word_id"] for r in review["rounds"] for card in r["exercises"]}
        ),
    }


def _set_due(db_session: Session, word_id: int, delta: timedelta) -> None:
    progress = db_session.get(Progress, word_id)
    progress.due_at = utcnow() + delta
    db_session.commit()


def test_group_study_leaves_main_learning_untouched(
    client: TestClient, db_session: Session, words: list[Word]
):
    new, learning, later, due, known, suspended = (w.id for w in words[:6])
    _ok(client.put(f"/api/words/{new}/priority", json={"priority": True}))
    _ok(client.put(f"/api/words/{learning}/status", json={"status": "learning"}))
    _ok(client.put(f"/api/words/{later}/status", json={"status": "review"}))
    _set_due(db_session, later, timedelta(days=10))
    _ok(client.put(f"/api/words/{due}/status", json={"status": "review"}))
    _set_due(db_session, due, timedelta(days=-1))
    _ok(client.put(f"/api/words/{known}/status", json={"status": "known"}))
    _ok(client.put(f"/api/words/{suspended}/status", json={"status": "suspended"}))
    # Десять слов — ровно две порции: в них побывают слова всех статусов
    label_id = _label(client, "десять", [w.id for w in words[:10]])

    before = _snapshot(client, db_session)
    assert before["learn"] and before["review"]

    played: set[int] = set()
    for _ in range(2):
        body = _session(client, label_id)
        portion = _portion(body)
        played |= set(portion)
        _play(client, db_session, body, wrong_for=set(portion[:2]))
        assert _finish(client, body["session_id"])

    assert {new, learning, later, due, known, suspended} <= played
    assert _snapshot(client, db_session) == before


def test_group_study_ignores_daily_new_limit(
    client: TestClient, db_session: Session, words: list[Word], monkeypatch
):
    monkeypatch.setattr(settings, "daily_new_limit", 1)
    _ok(client.post("/api/study/select", json={"word_id": words[0].id, "action": "learn"}))
    assert _ok(client.get("/api/study/session", params={"mode": "learn"}))["new_words"] == []

    label_id = _label(client, "всё", [w.id for w in words])
    for _ in range(20):
        body = _session(client, label_id)
        assert body["session_id"]
        _play(client, db_session, body)
        _finish(client, body["session_id"])


# ------------------------------------------------------------------ круг (US3)


def test_portions_walk_the_whole_group(
    client: TestClient, db_session: Session, words: list[Word]
):
    label_id = _label(client, "всё", [w.id for w in words])

    first, _ = _study(client, db_session, label_id)
    assert (_groups(client)[label_id]["done"], _groups(client)[label_id]["cycle"]) == (5, 1)
    second, _ = _study(client, db_session, label_id)
    assert (_groups(client)[label_id]["done"], _groups(client)[label_id]["cycle"]) == (10, 1)
    assert not set(_portion(first)) & set(_portion(second))

    third = _session(client, label_id)
    portion = _portion(third)
    remainder = {w.id for w in words} - set(_portion(first)) - set(_portion(second))
    assert len(portion) == len(set(portion)) == 5
    assert remainder < set(portion)
    _play(client, db_session, third)
    _finish(client, third["session_id"])

    # Круг 1 закрыт остатком, во втором пройдены три добранных слова
    group = _groups(client)[label_id]
    assert (group["word_count"], group["done"], group["cycle"]) == (12, 3, 2)


def test_full_cycle_starts_the_next_one(
    client: TestClient, db_session: Session, words: list[Word]
):
    label_id = _label(client, "кухня", [w.id for w in words[:5]])
    _study(client, db_session, label_id)
    assert (_groups(client)[label_id]["done"], _groups(client)[label_id]["cycle"]) == (5, 1)

    body = _session(client, label_id)
    assert (body["done"], body["cycle"]) == (0, 2)
    assert sorted(_portion(body)) == sorted(w.id for w in words[:5])


def test_interrupted_portion_comes_back(
    client: TestClient, db_session: Session, words: list[Word]
):
    label_id = _label(client, "всё", [w.id for w in words])
    body = _session(client, label_id)
    word = db_session.get(Word, _portion(body)[0])
    _answer(client, label_id, body["session_id"], word.id, "choice_ru_en", word.word)

    again = _session(client, label_id)
    assert set(_portion(again)) == set(_portion(body))
    assert again["session_id"] != body["session_id"]


def test_interrupted_seam_portion_comes_back(
    client: TestClient, db_session: Session, words: list[Word]
):
    label_id = _label(client, "семь", [w.id for w in words[:7]])
    _study(client, db_session, label_id)

    seam = _session(client, label_id)
    again = _session(client, label_id)
    assert len(_portion(seam)) == 5
    assert set(_portion(again)) == set(_portion(seam))


def test_two_labels_keep_their_own_cycles(
    client: TestClient, db_session: Session, words: list[Word]
):
    shared = words[0].id
    first = _label(client, "первая", [shared, words[1].id])
    second = _label(client, "вторая", [shared, words[2].id])

    _study(client, db_session, first)
    groups = _groups(client)
    assert groups[first]["done"] == 2
    assert groups[second]["done"] == 0
    assert shared in _portion(_session(client, second))


def test_finish_is_idempotent(client: TestClient, db_session: Session, words: list[Word]):
    label_id = _label(client, "семь", [w.id for w in words[:7]])
    _study(client, db_session, label_id)
    body, results = _study(client, db_session, label_id)  # стык кругов
    groups = _groups(client)

    assert _finish(client, body["session_id"]) == results
    assert _groups(client) == groups


def test_new_member_joins_the_current_cycle(
    client: TestClient, db_session: Session, words: list[Word]
):
    newcomer = words[11].id
    label_id = _label(client, "всё", [w.id for w in words[:11]])
    _study(client, db_session, label_id)

    _tag(client, newcomer, "всё")
    assert _groups(client)[label_id]["word_count"] == 12

    seen: list[int] = []
    while _groups(client)[label_id]["cycle"] == 1:
        body, _ = _study(client, db_session, label_id)
        seen += _portion(body)
    assert newcomer in seen


def test_word_that_lost_the_label_leaves_the_group(
    client: TestClient, db_session: Session, words: list[Word]
):
    label_id = _label(client, "всё", [w.id for w in words])
    body = _session(client, label_id)
    gone = _portion(body)[0]
    _untag(client, gone, "всё")

    assert _groups(client)[label_id]["word_count"] == 11
    # Посреди занятия: по слову больше не отвечают
    word = db_session.get(Word, gone)
    response = _answer_raw(client, label_id, body["session_id"], gone, "letters", word.word)
    assert response.status_code == 409

    for _ in range(3):
        portion, _ = _study(client, db_session, label_id)
        assert gone not in _portion(portion)


def test_deleting_word_or_label_removes_cycle_rows(
    client: TestClient, db_session: Session, words: list[Word]
):
    assert db_session.execute(text("PRAGMA foreign_keys")).scalar() == 1
    label_id = _label(client, "кухня", [w.id for w in words[:3]])
    other = _label(client, "посуда", [w.id for w in words[3:5]])
    _session(client, label_id)
    _session(client, other)

    def rows(**where) -> int:
        stmt = select(func.count()).select_from(GroupCycleWord)
        for column, value in where.items():
            stmt = stmt.where(getattr(GroupCycleWord, column) == value)
        return db_session.scalar(stmt) or 0

    assert rows(word_id=words[0].id) == 1
    _ok(client.delete(f"/api/words/{words[0].id}"), 204)
    assert rows(word_id=words[0].id) == 0

    _ok(client.delete(f"/api/labels/{label_id}"), 204)
    assert rows(label_id=label_id) == 0
    assert rows(label_id=other) == 2


def test_renamed_label_keeps_its_cycle(
    client: TestClient, db_session: Session, words: list[Word]
):
    label_id = _label(client, "всё", [w.id for w in words])
    _study(client, db_session, label_id)
    before = _groups(client)[label_id]

    _ok(client.patch(f"/api/labels/{label_id}", json={"name": "Все слова"}))
    after = _groups(client)[label_id]
    assert after == {**before, "name": "Все слова"}


# ------------------------------------------------------------ круг заново (US4)


def test_restart_starts_a_new_cycle(client: TestClient, db_session: Session, words: list[Word]):
    for word in words[:4]:
        _ok(client.put(f"/api/words/{word.id}/status", json={"status": "review"}))
    label_id = _label(client, "всё", [w.id for w in words])
    _study(client, db_session, label_id)
    db_session.expire_all()
    progress = db_session.execute(text("SELECT * FROM progress ORDER BY word_id")).all()
    assert _groups(client)[label_id]["done"] == 5

    _ok(client.post(f"/api/group-study/groups/{label_id}/restart"), 204)

    group = _groups(client)[label_id]
    assert (group["word_count"], group["done"], group["cycle"]) == (12, 0, 2)
    db_session.expire_all()
    assert db_session.execute(text("SELECT * FROM progress ORDER BY word_id")).all() == progress

    body = _session(client, label_id)
    assert (body["done"], body["cycle"]) == (0, 2)


def test_restart_errors_and_empty_group(client: TestClient, db_session: Session):
    assert client.post("/api/group-study/groups/999/restart").status_code == 404

    label_id = _label(client, "пусто", [])
    _ok(client.post(f"/api/group-study/groups/{label_id}/restart"), 204)
    assert _count(db_session, GroupCycleWord) == 0


@pytest.mark.parametrize("exercise", ["choice_ru_en", "dictation"])
def test_hint_is_logged_like_normal_sessions(
    client: TestClient, db_session: Session, words: list[Word], exercise: str
):
    word = words[0]
    label_id = _label(client, "кухня", [word.id])
    session_id = _session(client, label_id)["session_id"]
    response = client.post(
        "/api/group-study/answer",
        json={
            "word_id": word.id,
            "label_id": label_id,
            "session_id": session_id,
            "exercise": exercise,
            "answer": word.word,
            "used_hint": True,
        },
    )
    assert _ok(response)["correct"] is True
    log = db_session.scalars(select(GroupReviewLog)).one()
    assert log.used_hint is True
    assert log.quality < 5
