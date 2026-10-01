"""Сквозные проверки API: полный цикл изучения слова и работа со словарём."""

from collections.abc import Callable
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.classifier import (
    ClassifierConfig,
    ClassifierError,
    LabelItem,
    WordItem,
    get_classifier,
    get_classifier_factory,
)
from app.clock import utcnow
from app.config import settings
from app.main import app
from app.models import (
    ExerciseType,
    Label,
    Progress,
    ReviewLog,
    Setting,
    Word,
    WordStatus,
    word_labels,
)
from app.srs import EXERCISE_ROUNDS


def _session(client: TestClient, mode: str):
    response = client.get("/api/study/session", params={"mode": mode})
    assert response.status_code == 200, response.text
    return response.json()


def _first_new_word(client: TestClient) -> dict:
    return _session(client, "learn")["new_words"][0]


def _answer(client: TestClient, word_id: int, exercise: str, answer: str, **extra):
    payload = {"word_id": word_id, "exercise": exercise, "answer": answer, **extra}
    response = client.post("/api/study/answer", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def _round_exercises(rounds: list[dict]) -> list[dict]:
    """Все упражнения плана занятия подряд — когда порядок раундов не важен."""
    return [exercise for round_ in rounds for exercise in round_["exercises"]]


def _rounds(client: TestClient, word_ids: list[int]) -> list[dict]:
    """План раундов по словам, взятым в изучение."""
    response = client.post("/api/study/rounds", json={"word_ids": word_ids})
    assert response.status_code == 200, response.text
    return response.json()


def _learn_session(client: TestClient, count: int = 5) -> tuple[str, list[int]]:
    """Пройти знакомство занятия-изучения: ключ занятия и взятые слова."""
    body = _session(client, "learn")
    started = [w["id"] for w in body["new_words"]][:count]
    for word_id in started:
        client.post("/api/study/select", json={"word_id": word_id, "action": "learn"})
    return body["session_id"], started


def _start(client: TestClient, count: int = 5) -> list[int]:
    """Взять в изучение `count` слов: они сразу становятся словами к повторению."""
    started = [w["id"] for w in _session(client, "learn")["new_words"]][:count]
    for word_id in started:
        client.post("/api/study/select", json={"word_id": word_id, "action": "learn"})
    return started


def _answers_of(words: list[Word], word_ids: list[int]) -> dict[int, dict[str, str]]:
    """Верный ответ каждого слова по типу упражнения.

    В раунде «англ→рус» ответом служит перевод, во всех остальных — само слово.
    """
    chosen = set(word_ids)
    return {
        word.id: {
            exercise: (word.translation if exercise == ExerciseType.CHOICE_EN_RU else word.word)
            for exercise in EXERCISE_ROUNDS
        }
        for word in words
        if word.id in chosen
    }


def _release(db_session: Session, word_ids: list[int], interval_days: float = 1.0) -> None:
    """Выпустить слова в режим повторений со сроком «вчера».

    Занятие-повторение берёт и learning, и review, но проверять SM-2 имеет
    смысл на выпущенных словах: у learning ответ двигает шаг, а не интервал.
    """
    for word_id in word_ids:
        progress = db_session.get(Progress, word_id)
        progress.status = WordStatus.REVIEW
        progress.step = 4
        progress.repetitions = 1
        progress.interval_days = interval_days
        progress.due_at = utcnow() - timedelta(days=1)
    db_session.commit()


def _finish(client: TestClient, session_id: str, mode: str = "review"):
    response = client.post(
        "/api/study/finish", json={"session_id": session_id, "mode": mode}
    )
    assert response.status_code == 200, response.text
    return response.json()


def _play_round(
    client: TestClient,
    session_id: str,
    round_: dict,
    answers: dict[int, dict[str, str]],
    wrong_for: int | None = None,
    mode: str = "review",
) -> int:
    """Пройти раунд целиком: верные ответы на все слова, кроме `wrong_for`.

    Ошибку тут же исправляем вторым показом — так занятие доходит до конца,
    как и требует FR-008. Возвращает число показанных карточек: повтор после
    ошибки удлиняет раунд.
    """
    exercise_type = round_["exercise"]
    shown = 0
    for exercise in round_["exercises"]:
        word_id = exercise["word_id"]
        if word_id == wrong_for:
            _answer(
                client,
                word_id,
                exercise_type,
                "заведомо неверно",
                mode=mode,
                session_id=session_id,
                attempt=1,
            )
            shown += 1
        _answer(
            client,
            word_id,
            exercise_type,
            answers[word_id][exercise_type],
            mode=mode,
            session_id=session_id,
            attempt=2 if word_id == wrong_for else 1,
        )
        shown += 1
    return shown


def test_health(client: TestClient):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_session_offers_new_words(client: TestClient, words: list[Word]):
    body = _session(client, "learn")

    assert len(body["new_words"]) == 5  # new_words_per_session
    # План изучения приходит отдельным запросом: до конца знакомства
    # неизвестно, какие слова в занятии останутся
    assert body["rounds"] == []
    assert body["counts"]["new"] == 5
    assert body["counts"]["in_study"] == 0


def test_learn_session_carries_a_session_key(client: TestClient, words: list[Word]):
    # Ключ занятия нужен и изучению: попытки раундов пишутся под ним,
    # и по нему же финиш собирает итог
    assert _session(client, "learn")["session_id"]

    for word in words:
        client.post("/api/study/select", json={"word_id": word.id, "action": "know"})

    empty = _session(client, "learn")
    assert empty["new_words"] == []
    assert empty["session_id"] is None


def test_full_learning_cycle(client: TestClient, db_session: Session, words: list[Word]):
    body = _session(client, "learn")
    session_id = body["session_id"]
    word_id = body["new_words"][0]["id"]

    # Знакомство: «Изучить» только заводит прогресс, упражнений с собой не несёт
    selected = client.post(
        "/api/study/select", json={"word_id": word_id, "action": "learn"}
    ).json()
    assert selected["progress"]["status"] == WordStatus.LEARNING
    assert selected["progress"]["step"] == 0

    rounds = _rounds(client, [word_id])
    answers = _answers_of(words, [word_id])
    for round_ in rounds:
        _play_round(client, session_id, round_, answers, mode="learn")

    # Четыре раунда позади, а слово всё ещё в изучении: итог подводит финиш
    db_session.expire_all()
    assert db_session.get(Progress, word_id).status == WordStatus.LEARNING

    results = _finish(client, session_id, mode="learn")
    assert [r["word_id"] for r in results] == [word_id]
    assert results[0]["progress"]["status"] == WordStatus.REVIEW
    assert results[0]["progress"]["repetitions"] == 1
    assert results[0]["progress"]["interval_days"] == 1.0

    db_session.expire_all()
    progress = db_session.get(Progress, word_id)
    assert timedelta(hours=20) < progress.due_at - utcnow() < timedelta(hours=28)

    logs = db_session.scalars(select(ReviewLog).where(ReviewLog.word_id == word_id)).all()
    assert [log.exercise for log in logs] == [ExerciseType.INTRO, *EXERCISE_ROUNDS]
    assert all(log.correct for log in logs)


def test_hint_lowers_quality(client: TestClient, db_session: Session, words: list[Word]):
    session_id, started = _learn_session(client, 1)
    word_id = started[0]
    spelling = db_session.get(Word, word_id).word

    result = _answer(
        client,
        word_id,
        ExerciseType.CHOICE_RU_EN,
        spelling,
        used_hint=True,
        mode="learn",
        session_id=session_id,
    )
    assert result["correct"] is True
    assert result["quality"] == 4


def test_already_known_word_leaves_rotation(
    client: TestClient, db_session: Session, words: list[Word]
):
    target = _first_new_word(client)
    word_id = target["id"]

    body = client.post("/api/study/select", json={"word_id": word_id, "action": "know"}).json()
    assert body["progress"]["status"] == WordStatus.KNOWN

    offered = {w["id"] for w in _session(client, "learn")["new_words"]}
    assert word_id not in offered


def test_session_mode_is_required(client: TestClient, words: list[Word]):
    assert client.get("/api/study/session").status_code == 422


def test_learn_mode_offers_only_new_words(client: TestClient, words: list[Word]):
    target = _first_new_word(client)
    client.post("/api/study/select", json={"word_id": target["id"], "action": "learn"})

    body = _session(client, "learn")

    # Взятое в работу слово ушло в повторение и в «учить» не попадает
    assert body["rounds"] == []
    assert target["id"] not in {w["id"] for w in body["new_words"]}
    assert len(body["new_words"]) == 5


def test_review_mode_offers_only_due_words(client: TestClient, words: list[Word]):
    started = _start(client)

    body = _session(client, "review")

    assert body["new_words"] == []
    assert {e["word_id"] for e in _round_exercises(body["rounds"])} == set(started)
    assert body["counts"]["learning"] == 5


def test_letters_exercise_keeps_the_bank_on_review(
    client: TestClient, db_session: Session, words: list[Word]
):
    word_id = _first_new_word(client)["id"]
    client.post("/api/study/select", json={"word_id": word_id, "action": "learn"})
    progress = db_session.get(Progress, word_id)
    progress.status = WordStatus.REVIEW
    progress.repetitions = 3
    progress.due_at = utcnow() - timedelta(days=1)
    db_session.commit()

    letters = [
        exercise
        for exercise in _round_exercises(_session(client, "review")["rounds"])
        if exercise["type"] == ExerciseType.LETTERS
    ]

    assert letters, "в плане занятия нет раунда со сборкой из букв"
    assert all(e["show_letters"] for e in letters)
    assert all(e["letters"] for e in letters)


def test_review_mode_is_capped_at_five_words(client: TestClient, words: list[Word]):
    # Двенадцати слов в словаре хватает, чтобы взять в работу больше пяти
    for word in words[:7]:
        client.post("/api/study/select", json={"word_id": word.id, "action": "learn"})

    body = _session(client, "review")

    # review_words_per_session
    assert len({e["word_id"] for e in _round_exercises(body["rounds"])}) == 5
    assert body["counts"]["in_study"] == 7


def test_known_word_is_replaced_by_the_next_new_one(client: TestClient, words: list[Word]):
    offered = _session(client, "learn")["new_words"]
    shown = [w["id"] for w in offered]

    body = client.post(
        "/api/study/select",
        json={"word_id": shown[0], "action": "know", "exclude_ids": shown},
    ).json()

    replacement = body["replacement"]
    assert replacement is not None
    assert replacement["id"] not in shown  # не повторяет уже показанные слова
    assert replacement["id"] == words[len(shown)].id  # следующее по порядку словаря


def test_learn_action_does_not_bring_a_replacement(client: TestClient, words: list[Word]):
    shown = [w["id"] for w in _session(client, "learn")["new_words"]]

    body = client.post(
        "/api/study/select",
        json={"word_id": shown[0], "action": "learn", "exclude_ids": shown},
    ).json()

    assert body["replacement"] is None


def test_replacement_is_absent_when_dictionary_runs_out(client: TestClient, db_session: Session):
    created = client.post("/api/words", json={"word": "quirk", "translation": "причуда"}).json()

    body = client.post(
        "/api/study/select",
        json={"word_id": created["id"], "action": "know", "exclude_ids": [created["id"]]},
    ).json()

    assert body["replacement"] is None


def test_session_rebuilds_after_reload(client: TestClient, words: list[Word]):
    body = _session(client, "learn")
    session_id = body["session_id"]
    target = body["new_words"][0]
    word_id, spelling = target["id"], target["word"]
    client.post("/api/study/select", json={"word_id": word_id, "action": "learn"})
    _answer(
        client,
        word_id,
        ExerciseType.CHOICE_RU_EN,
        spelling,
        mode="learn",
        session_id=session_id,
    )

    # Перезагрузка страницы = повторный запрос сессии; прогресс не теряется
    body = _session(client, "review")
    pending = [e for e in _round_exercises(body["rounds"]) if e["word_id"] == word_id]
    # Слово ждёт в каждом раунде: занятие пересобирается целиком
    assert [e["type"] for e in pending] == list(EXERCISE_ROUNDS)
    assert body["counts"]["learning"] == 1


def test_answer_for_word_not_in_study_is_rejected(client: TestClient, words: list[Word]):
    response = client.post(
        "/api/study/answer",
        json={
            "word_id": words[0].id,
            "exercise": ExerciseType.DICTATION,
            "answer": "x",
            "session_id": "занятие",
        },
    )
    assert response.status_code == 409


def test_reset_returns_word_to_new(client: TestClient, words: list[Word]):
    word_id = _first_new_word(client)["id"]
    client.post("/api/study/select", json={"word_id": word_id, "action": "learn"})

    assert client.post(f"/api/study/reset/{word_id}").status_code == 204
    assert client.get(f"/api/words/{word_id}").json()["progress"] is None


def test_create_word_and_reject_the_same_meaning(client: TestClient):
    created = client.post(
        "/api/words",
        json={"word": " Serendipity ", "translation": "счастливая случайность"},
    )
    assert created.status_code == 201
    assert created.json()["word"] == "Serendipity"

    duplicate = client.post(
        "/api/words",
        json={"word": "serendipity", "translation": "СЧАСТЛИВАЯ  СЛУЧАЙНОСТЬ"},
    )
    assert duplicate.status_code == 409
    assert "уже есть" in duplicate.json()["detail"]


def test_create_word_allows_another_meaning(client: TestClient):
    first = client.post("/api/words", json={"word": "roll out", "translation": "вылезать"})
    second = client.post(
        "/api/words",
        json={
            "word": "roll out",
            "translation": "внедрить",
            "example": "The school will roll out a new platform.",
        },
    )

    assert second.status_code == 201
    assert second.json()["id"] != first.json()["id"]

    listed = client.get("/api/words", params={"search": "roll out"}).json()
    assert [w["translation"] for w in listed["items"]] == ["вылезать", "внедрить"]
    # Каждое значение учится само по себе — оба попадают в занятие
    offered = {w["id"] for w in _session(client, "learn")["new_words"]}
    assert {first.json()["id"], second.json()["id"]} <= offered


def test_meanings_of_one_word_keep_separate_progress(client: TestClient):
    first = client.post("/api/words", json={"word": "roll out", "translation": "вылезать"}).json()
    second = client.post("/api/words", json={"word": "roll out", "translation": "внедрить"}).json()

    client.post("/api/study/select", json={"word_id": first["id"], "action": "learn"})

    assert client.get(f"/api/words/{first['id']}").json()["progress"]["status"] == (
        WordStatus.LEARNING
    )
    assert client.get(f"/api/words/{second['id']}").json()["progress"] is None


def test_update_word_rejects_meaning_of_a_twin(client: TestClient):
    client.post("/api/words", json={"word": "roll out", "translation": "вылезать"})
    second = client.post(
        "/api/words", json={"word": "roll out", "translation": "внедрить"}
    ).json()

    clash = client.patch(f"/api/words/{second['id']}", json={"translation": "вылезать"})
    assert clash.status_code == 409

    # Правка, не задевающая соседнее значение, проходит
    ok = client.patch(f"/api/words/{second['id']}", json={"translation": "развернуть"})
    assert ok.status_code == 200
    assert ok.json()["translation"] == "развернуть"


def test_new_word_is_offered_for_study(client: TestClient, db_session: Session):
    created = client.post(
        "/api/words", json={"word": "quirk", "translation": "причуда"}
    ).json()

    offered = {w["id"] for w in _session(client, "learn")["new_words"]}
    assert created["id"] in offered


def test_update_and_delete_word(client: TestClient, db_session: Session, words: list[Word]):
    word_id = words[0].id

    patched = client.patch(f"/api/words/{word_id}", json={"translation": "новый перевод"})
    assert patched.status_code == 200
    assert patched.json()["translation"] == "новый перевод"

    assert client.delete(f"/api/words/{word_id}").status_code == 204
    assert client.get(f"/api/words/{word_id}").status_code == 404


def test_deleting_word_removes_progress(
    client: TestClient, db_session: Session, words: list[Word]
):
    word_id = _first_new_word(client)["id"]
    client.post("/api/study/select", json={"word_id": word_id, "action": "learn"})

    client.delete(f"/api/words/{word_id}")
    db_session.expire_all()
    assert db_session.get(Progress, word_id) is None


def test_status_change_takes_a_word_out_of_rotation(client: TestClient, words: list[Word]):
    word_id = _first_new_word(client)["id"]
    client.post("/api/study/select", json={"word_id": word_id, "action": "learn"})

    known = client.put(f"/api/words/{word_id}/status", json={"status": WordStatus.KNOWN})
    assert known.status_code == 200
    assert known.json()["progress"]["status"] == WordStatus.KNOWN
    # Выведенное из оборота слово не попадает ни в новые, ни в повторение
    assert word_id not in {w["id"] for w in _session(client, "learn")["new_words"]}
    due = _round_exercises(_session(client, "review")["rounds"])
    assert word_id not in {e["word_id"] for e in due}


def test_status_change_releases_a_new_word_into_review(client: TestClient, words: list[Word]):
    word_id = words[0].id

    body = client.put(f"/api/words/{word_id}/status", json={"status": WordStatus.REVIEW}).json()

    assert body["progress"]["status"] == WordStatus.REVIEW
    assert body["progress"]["repetitions"] == 1
    assert body["progress"]["interval_days"] == 1.0


def test_suspended_word_keeps_its_schedule(client: TestClient, words: list[Word]):
    word_id = words[0].id
    released = client.put(
        f"/api/words/{word_id}/status", json={"status": WordStatus.REVIEW}
    ).json()

    client.put(f"/api/words/{word_id}/status", json={"status": WordStatus.SUSPENDED})
    back = client.put(f"/api/words/{word_id}/status", json={"status": WordStatus.REVIEW}).json()

    assert back["progress"]["due_at"] == released["progress"]["due_at"]
    assert back["progress"]["ease"] == released["progress"]["ease"]


def test_status_new_drops_the_progress(client: TestClient, words: list[Word]):
    word_id = _first_new_word(client)["id"]
    client.post("/api/study/select", json={"word_id": word_id, "action": "learn"})

    body = client.put(f"/api/words/{word_id}/status", json={"status": "new"}).json()

    assert body["progress"] is None
    assert word_id in {w["id"] for w in _session(client, "learn")["new_words"]}


def test_unknown_status_is_rejected(client: TestClient, words: list[Word]):
    response = client.put(f"/api/words/{words[0].id}/status", json={"status": "выучено"})
    assert response.status_code == 422


def test_words_search_and_status_filter(client: TestClient, words: list[Word]):
    # «outsid» — подстрока и outsider, и outside
    prefix = client.get("/api/words", params={"search": "outsid"}).json()
    assert {item["word"] for item in prefix["items"]} == {"outsider", "outside"}

    found = client.get("/api/words", params={"search": "outsider"}).json()
    assert found["total"] == 1
    assert found["items"][0]["word"] == "outsider"

    by_translation = client.get("/api/words", params={"search": "край"}).json()
    assert by_translation["total"] == 1

    word_id = _first_new_word(client)["id"]
    client.post("/api/study/select", json={"word_id": word_id, "action": "learn"})

    learning = client.get("/api/words", params={"status": "learning"}).json()
    assert learning["total"] == 1
    new_only = client.get("/api/words", params={"status": "new"}).json()
    assert new_only["total"] == len(words) - 1


def test_stats_overview_tracks_progress(client: TestClient, words: list[Word]):
    empty = client.get("/api/stats/overview").json()
    assert empty["total_words"] == len(words)
    assert empty["new"] == len(words)
    assert empty["streak_days"] == 0

    word_id = _first_new_word(client)["id"]
    client.post("/api/study/select", json={"word_id": word_id, "action": "learn"})

    after = client.get("/api/stats/overview").json()
    assert after["learning"] == 1
    assert after["new"] == len(words) - 1
    assert after["answers_today"] == 1
    assert after["new_today"] == 1
    assert after["streak_days"] == 1
    assert after["due_now"] == 1


def test_stats_daily_covers_requested_window(client: TestClient, words: list[Word]):
    word_id = _first_new_word(client)["id"]
    client.post("/api/study/select", json={"word_id": word_id, "action": "learn"})

    daily = client.get("/api/stats/daily", params={"days": 7}).json()
    assert len(daily) == 7
    assert daily[-1]["date"] == utcnow().date().isoformat()
    assert daily[-1]["answers"] == 1
    assert daily[-1]["correct"] == 1
    assert daily[-1]["accuracy"] == 1.0
    assert daily[-1]["new_words"] == 1


# ------------------------------------------------- занятие-повторение раундами


def test_review_session_is_a_plan_of_four_rounds(client: TestClient, words: list[Word]):
    started = _start(client)

    body = _session(client, "review")

    assert body["session_id"]
    assert [r["exercise"] for r in body["rounds"]] == list(EXERCISE_ROUNDS)
    for round_ in body["rounds"]:
        # В раунде — по одному упражнению своего типа на каждое слово занятия
        assert {e["word_id"] for e in round_["exercises"]} == set(started)
        assert {e["type"] for e in round_["exercises"]} == {round_["exercise"]}


def _orders(rounds: list[dict]) -> list[list[int]]:
    """Порядок слов в каждом раунде плана."""
    return [[e["word_id"] for e in round_["exercises"]] for round_ in rounds]


def _assert_rounds_reshuffled(orders: list[list[int]], words: list[int]) -> None:
    """Гарантии порядка из контракта плана: FR-003, FR-004, FR-006."""
    for order in orders:
        assert sorted(order) == sorted(words)
    for k in range(1, len(orders)):
        # FR-003: порядок раунда не повторяет предыдущий
        assert orders[k] != orders[k - 1]
        # FR-004: на стыке раундов одно слово не идёт дважды подряд
        if len(words) >= 3:
            assert orders[k][0] != orders[k - 1][-1]


def test_review_rounds_differ_in_order(client: TestClient, words: list[Word]):
    started = _start(client)

    # План случайный: гарантии проверяем на нескольких планах подряд
    for _ in range(20):
        _assert_rounds_reshuffled(_orders(_session(client, "review")["rounds"]), started)


def test_review_session_is_empty_without_due_words(client: TestClient, words: list[Word]):
    body = _session(client, "review")

    assert body["rounds"] == []
    assert body["session_id"] is None


def test_review_plan_holds_four_exercises_per_word(client: TestClient, words: list[Word]):
    started = _start(client)

    body = _session(client, "review")
    exercises = _round_exercises(body["rounds"])

    # SC-001, SC-002: занятие — это «слов × 4», сгруппированных по типу
    assert len(exercises) == len(started) * len(EXERCISE_ROUNDS)
    assert [r["exercise"] for r in body["rounds"]] == list(EXERCISE_ROUNDS)


def test_review_answer_logs_the_attempt_without_touching_the_schedule(
    client: TestClient, db_session: Session, words: list[Word]
):
    word_id = _start(client, 1)[0]
    spelling = db_session.get(Word, word_id).word
    body = _session(client, "review")
    session_id = body["session_id"]

    before = db_session.get(Progress, word_id)
    snapshot = (before.status, before.due_at, before.ease, before.lapses, before.step)

    result = _answer(
        client,
        word_id,
        EXERCISE_ROUNDS[0],
        spelling,
        mode="review",
        session_id=session_id,
    )

    # FR-013a: внутри занятия расписание не двигается
    assert result["correct"] is True
    db_session.expire_all()
    after = db_session.get(Progress, word_id)
    assert (after.status, after.due_at, after.ease, after.lapses, after.step) == snapshot
    assert result["progress"]["due_at"] == before.due_at.isoformat()

    logged = db_session.scalars(
        select(ReviewLog).where(ReviewLog.session_id == session_id)
    ).all()
    assert [log.word_id for log in logged] == [word_id]
    assert logged[0].exercise == EXERCISE_ROUNDS[0]
    assert logged[0].status_before == logged[0].status_after


def test_finish_moves_the_schedule_once_for_a_clean_session(
    client: TestClient, db_session: Session, words: list[Word]
):
    started = _start(client)
    answers = _answers_of(words, started)
    _release(db_session, started)
    body = _session(client, "review")
    session_id = body["session_id"]

    for round_ in body["rounds"]:
        _play_round(client, session_id, round_, answers)

    # Четыре раунда позади, а расписание всё ещё прежнее
    db_session.expire_all()
    assert all(db_session.get(Progress, w).due_at < utcnow() for w in started)

    results = _finish(client, session_id)

    assert {r["word_id"] for r in results} == set(started)
    for result in results:
        assert result["mistakes"] == 0
        assert result["quality"] == 5
        # SC-005: сдвиг ровно такой, какой давал один верный ответ до доработки
        assert result["progress"]["status"] == WordStatus.REVIEW
        assert result["progress"]["repetitions"] == 2
        assert result["progress"]["interval_days"] == 3.0  # SECOND_INTERVAL_DAYS

    db_session.expire_all()
    for word_id in started:
        progress = db_session.get(Progress, word_id)
        # Три дня плюс-минус джиттер: срок ушёл в будущее ровно один раз
        assert timedelta(days=2.5) < progress.due_at - utcnow() < timedelta(days=3.5)


def test_finish_is_idempotent_and_skips_unfinished_words(
    client: TestClient, db_session: Session, words: list[Word]
):
    started = _start(client, 2)
    answers = _answers_of(words, started)
    _release(db_session, started)
    body = _session(client, "review")
    session_id = body["session_id"]
    done, abandoned = started

    # Первое слово проходит все четыре раунда, второе — только первый
    for index, round_ in enumerate(body["rounds"]):
        for exercise in round_["exercises"]:
            if exercise["word_id"] == abandoned and index > 0:
                continue
            _answer(
                client,
                exercise["word_id"],
                round_["exercise"],
                answers[exercise["word_id"]][round_["exercise"]],
                mode="review",
                session_id=session_id,
            )

    db_session.expire_all()
    untouched = db_session.get(Progress, abandoned)
    snapshot = (untouched.status, untouched.due_at, untouched.step, untouched.updated_at)

    results = _finish(client, session_id)

    # FR-017a: незавершённое слово не упоминается и не меняется
    assert [r["word_id"] for r in results] == [done]
    db_session.expire_all()
    after = db_session.get(Progress, abandoned)
    assert (after.status, after.due_at, after.step, after.updated_at) == snapshot

    db_session.expire_all()
    settled = db_session.get(Progress, done).due_at

    # Повторный вызов ничего не пересчитывает второй раз
    assert _finish(client, session_id) == []
    db_session.expire_all()
    assert db_session.get(Progress, done).due_at == settled


@pytest.mark.parametrize("mode", ["learn", "review"])
def test_answer_without_session_id_is_rejected(client: TestClient, words: list[Word], mode: str):
    # Без ключа занятия попытку некуда записать, и финиш не соберёт итог
    word_id = _start(client, 1)[0]

    response = client.post(
        "/api/study/answer",
        json={
            "word_id": word_id,
            "exercise": EXERCISE_ROUNDS[0],
            "answer": "x",
            "mode": mode,
        },
    )
    assert response.status_code == 422


def test_finish_of_an_unknown_session_is_not_an_error(client: TestClient, words: list[Word]):
    # Занятие, в котором не было ни одного ответа, — не ошибка
    assert _finish(client, "нет такого занятия") == []


def test_wrong_review_answer_returns_a_freshly_built_card(
    client: TestClient, db_session: Session, words: list[Word]
):
    word_id = _start(client, 1)[0]
    spelling = db_session.get(Word, word_id).word
    body = _session(client, "review")
    session_id = body["session_id"]
    letters_round = next(r for r in body["rounds"] if r["exercise"] == ExerciseType.LETTERS)
    original = letters_round["exercises"][0]

    missed = _answer(
        client,
        word_id,
        ExerciseType.LETTERS,
        "заведомо неверно",
        mode="review",
        session_id=session_id,
    )

    # FR-006, FR-006a: тот же тип, но карточка собрана заново
    assert missed["correct"] is False
    assert missed["repeat_in_session"] is True
    assert missed["next_exercise"]["type"] == ExerciseType.LETTERS
    assert missed["next_exercise"]["word_id"] == word_id
    assert missed["next_exercise"]["letters"] != original["letters"]

    fixed = _answer(
        client,
        word_id,
        ExerciseType.LETTERS,
        spelling,
        mode="review",
        session_id=session_id,
        attempt=2,
    )
    assert fixed["correct"] is True
    assert fixed["repeat_in_session"] is False
    assert fixed["next_exercise"] is None


def test_a_single_mistake_sends_the_word_back_to_learning(
    client: TestClient, db_session: Session, words: list[Word]
):
    started = _start(client, 2)
    answers = _answers_of(words, started)
    # Слово выпущено в повторение: только оттуда виден откат и рост lapses
    _release(db_session, started)

    body = _session(client, "review")
    session_id = body["session_id"]
    stumbled, clean = started

    # Ошибка в первом раунде, исправленная тут же
    _play_round(client, session_id, body["rounds"][0], answers, wrong_for=stumbled)
    for round_ in body["rounds"][1:]:
        _play_round(client, session_id, round_, answers)

    results = {r["word_id"]: r for r in _finish(client, session_id)}

    # FR-014, SC-006: исправленная ошибка всё равно считается забыванием
    assert results[stumbled]["mistakes"] == 1
    assert results[stumbled]["quality"] == 2
    assert results[stumbled]["progress"]["status"] == WordStatus.LEARNING
    assert results[stumbled]["progress"]["lapses"] == 1
    db_session.expire_all()
    assert db_session.get(Progress, stumbled).due_at <= utcnow()

    # Соседнее слово занятия не задето
    assert results[clean]["mistakes"] == 0
    assert results[clean]["progress"]["status"] == WordStatus.REVIEW
    assert db_session.get(Progress, clean).due_at > utcnow()


# --------------------------------------------------- занятие-изучение раундами


def test_learn_rounds_cover_every_word_in_every_type(client: TestClient, words: list[Word]):
    _, started = _learn_session(client)

    rounds = _rounds(client, started)

    assert [r["exercise"] for r in rounds] == list(EXERCISE_ROUNDS)
    for round_ in rounds:
        # В раунде — по одному упражнению своего типа на каждое слово занятия
        # FR-006: каждое слово ровно по разу, но порядок у раунда свой
        assert sorted(e["word_id"] for e in round_["exercises"]) == sorted(started)
        assert {e["type"] for e in round_["exercises"]} == {round_["exercise"]}
    # FR-007: карточка-знакомство в раунды не попадает
    assert ExerciseType.INTRO not in {e["type"] for e in _round_exercises(rounds)}


def test_learn_rounds_skip_words_that_left_the_rotation(client: TestClient, words: list[Word]):
    # FR-019: все слова занятия могли оказаться знакомыми — это не ошибка
    assert _rounds(client, []) == []

    _, started = _learn_session(client)
    known, deleted, alive = started[0], started[1], started[2:]
    client.put(f"/api/words/{known}/status", json={"status": WordStatus.KNOWN})
    client.delete(f"/api/words/{deleted}")

    rounds = _rounds(client, started)

    # FR-020: слово могли вывести из оборота между знакомством и планом раундов
    assert [r["exercise"] for r in rounds] == list(EXERCISE_ROUNDS)
    for round_ in rounds:
        assert sorted(e["word_id"] for e in round_["exercises"]) == sorted(alive)

    for word_id in alive:
        client.put(f"/api/words/{word_id}/status", json={"status": WordStatus.KNOWN})
    assert _rounds(client, started) == []


def test_learn_rounds_differ_in_order(client: TestClient, words: list[Word]):
    _, started = _learn_session(client)

    for _ in range(20):
        _assert_rounds_reshuffled(_orders(_rounds(client, started)), started)

    # FR-005: у двух слов второй порядок один — раунды чередуют два порядка
    pair = _orders(_rounds(client, started[:2]))
    for k in range(1, len(pair)):
        assert pair[k] == pair[k - 1][::-1]


def test_learn_answer_logs_the_attempt_without_touching_the_schedule(
    client: TestClient, db_session: Session, words: list[Word]
):
    session_id, started = _learn_session(client, 1)
    word_id = started[0]
    spelling = db_session.get(Word, word_id).word

    before = db_session.get(Progress, word_id)
    snapshot = (
        before.status,
        before.due_at,
        before.ease,
        before.lapses,
        before.step,
        before.updated_at,
    )

    result = _answer(
        client,
        word_id,
        EXERCISE_ROUNDS[0],
        spelling,
        mode="learn",
        session_id=session_id,
    )

    # FR-015a: ответ внутри занятия только пишется в журнал
    assert result["correct"] is True
    assert result["progress"]["status"] == WordStatus.LEARNING
    db_session.expire_all()
    after = db_session.get(Progress, word_id)
    assert (
        after.status,
        after.due_at,
        after.ease,
        after.lapses,
        after.step,
        after.updated_at,
    ) == snapshot

    # Попытка занятия помечена его ключом; карточка знакомства — нет,
    # она в раунды не входит и на финиш не влияет
    logged = db_session.scalars(
        select(ReviewLog).where(ReviewLog.session_id == session_id)
    ).all()
    assert [log.word_id for log in logged] == [word_id]
    assert logged[0].exercise == EXERCISE_ROUNDS[0]
    assert logged[0].status_before == logged[0].status_after


def test_wrong_learn_answer_repeats_the_same_type(
    client: TestClient, db_session: Session, words: list[Word]
):
    session_id, started = _learn_session(client, 1)
    word_id = started[0]
    spelling = db_session.get(Word, word_id).word
    rounds = _rounds(client, started)
    original = next(r for r in rounds if r["exercise"] == ExerciseType.LETTERS)["exercises"][0]

    missed = _answer(
        client,
        word_id,
        ExerciseType.LETTERS,
        "заведомо неверно",
        mode="learn",
        session_id=session_id,
    )

    # FR-008, FR-008a: ошибка повторяет тот же тип упражнения — не откатывает
    # на предыдущий, — а карточка к повтору собирается заново
    assert missed["correct"] is False
    assert missed["correct_answer"] == spelling
    assert missed["quality"] == 2
    assert missed["repeat_in_session"] is True
    assert missed["next_exercise"]["type"] == ExerciseType.LETTERS
    assert missed["next_exercise"]["word_id"] == word_id
    assert missed["next_exercise"]["letters"] != original["letters"]

    # Прогресс слова ошибка не двигает: ни шага, ни статуса
    assert missed["progress"]["status"] == WordStatus.LEARNING
    assert missed["progress"]["step"] == 0
    db_session.expire_all()
    progress = db_session.get(Progress, word_id)
    assert (progress.status, progress.step) == (WordStatus.LEARNING, 0)


def test_a_clean_learn_session_is_four_rounds_of_five(
    client: TestClient, words: list[Word]
):
    session_id, started = _learn_session(client)
    answers = _answers_of(words, started)

    rounds = _rounds(client, started)
    shown = sum(
        _play_round(client, session_id, round_, answers, mode="learn") for round_ in rounds
    )

    # SC-001, SC-003: 20 карточек упражнений — по слову в каждом из четырёх
    # раундов, и тип меняется только на границе раунда
    assert shown == len(started) * len(EXERCISE_ROUNDS) == 20
    assert [r["exercise"] for r in rounds] == list(EXERCISE_ROUNDS)
    assert all(len(round_["exercises"]) == len(started) for round_ in rounds)
    assert ExerciseType.INTRO not in {e["type"] for e in _round_exercises(rounds)}


def test_learn_finish_releases_a_word_that_passed_every_round(
    client: TestClient, db_session: Session, words: list[Word]
):
    session_id, started = _learn_session(client, 2)
    answers = _answers_of(words, started)
    rounds = _rounds(client, started)
    done, abandoned = started

    # Первое слово проходит все четыре раунда, второе — только первый
    for index, round_ in enumerate(rounds):
        for exercise in round_["exercises"]:
            word_id = exercise["word_id"]
            if word_id == abandoned and index > 0:
                continue
            _answer(
                client,
                word_id,
                round_["exercise"],
                answers[word_id][round_["exercise"]],
                mode="learn",
                session_id=session_id,
            )

    db_session.expire_all()
    untouched = db_session.get(Progress, abandoned)
    snapshot = (untouched.status, untouched.step, untouched.due_at, untouched.updated_at)

    results = _finish(client, session_id, mode="learn")

    # FR-015: слово, прошедшее четыре раунда, выпускается в повторения
    assert [r["word_id"] for r in results] == [done]
    assert results[0]["progress"]["status"] == WordStatus.REVIEW
    assert results[0]["progress"]["repetitions"] == 1
    assert results[0]["progress"]["interval_days"] == 1.0

    db_session.expire_all()
    released = db_session.get(Progress, done)
    assert timedelta(hours=20) < released.due_at - utcnow() < timedelta(hours=28)

    # FR-016: брошенное посреди занятия слово остаётся в изучении
    after = db_session.get(Progress, abandoned)
    assert (after.status, after.step, after.due_at, after.updated_at) == snapshot


def test_learn_finish_treats_a_mistake_like_a_clean_answer(
    client: TestClient, db_session: Session, words: list[Word]
):
    session_id, started = _learn_session(client, 2)
    answers = _answers_of(words, started)
    rounds = _rounds(client, started)
    stumbled, clean = started

    _play_round(client, session_id, rounds[0], answers, wrong_for=stumbled, mode="learn")
    for round_ in rounds[1:]:
        _play_round(client, session_id, round_, answers, mode="learn")

    results = {r["word_id"]: r for r in _finish(client, session_id, mode="learn")}

    # FR-015b, SC-006, SC-007: ошибка уже закрыта верным ответом в том же раунде,
    # и расписанием её не наказывают — в отличие от повторения
    assert results[stumbled]["mistakes"] == 1
    assert results[clean]["mistakes"] == 0
    for word_id in started:
        progress = results[word_id]["progress"]
        assert progress["status"] == WordStatus.REVIEW
        assert progress["repetitions"] == 1
        assert progress["interval_days"] == 1.0
        assert progress["lapses"] == 0
    assert results[stumbled]["progress"]["ease"] == results[clean]["progress"]["ease"]


# ------------------------------------------------------------ порядок новых слов


def _set_order(client: TestClient, order: str) -> None:
    response = client.put("/api/settings", json={"new_words_order": order})
    assert response.status_code == 200, response.text


def _ids_in_order(words: list[Word], order: str) -> list[int]:
    """Слова фикстуры в порядке, в котором их должно брать «Изучение»."""
    ids = [w.id for w in words]
    return ids if order == "oldest_first" else ids[::-1]


def test_settings_default_to_the_order_of_addition(client: TestClient):
    # FR-002: пока настройку не трогали, поведение прежнее
    response = client.get("/api/settings")
    assert response.status_code == 200
    assert response.json() == {"new_words_order": "oldest_first"}


def test_settings_keep_the_chosen_order(client: TestClient):
    response = client.put("/api/settings", json={"new_words_order": "newest_first"})

    assert response.status_code == 200
    assert response.json() == {"new_words_order": "newest_first"}
    # FR-003: выбор хранится на сервере, а не в браузере
    assert client.get("/api/settings").json() == {"new_words_order": "newest_first"}


@pytest.mark.parametrize("payload", [{"new_words_order": "random"}, {}])
def test_settings_reject_an_unknown_order(client: TestClient, payload: dict):
    assert client.put("/api/settings", json=payload).status_code == 422


@pytest.mark.parametrize("order", ["oldest_first", "newest_first"])
def test_learn_session_follows_the_chosen_order(
    client: TestClient, words: list[Word], order: str
):
    _set_order(client, order)

    offered = [w["id"] for w in _session(client, "learn")["new_words"]]

    # FR-004, SC-001, SC-004
    assert offered == _ids_in_order(words, order)[:5]


def test_replacement_follows_the_chosen_order(client: TestClient, words: list[Word]):
    _set_order(client, "newest_first")
    shown = [w["id"] for w in _session(client, "learn")["new_words"]]

    body = client.post(
        "/api/study/select",
        json={"word_id": shown[0], "action": "know", "exclude_ids": shown},
    ).json()

    # Шестое с конца: пять последних уже показаны
    assert body["replacement"]["id"] == words[-6].id


def test_new_words_endpoint_follows_the_chosen_order(client: TestClient, words: list[Word]):
    _set_order(client, "newest_first")

    response = client.get("/api/study/new", params={"limit": 3})

    assert [w["id"] for w in response.json()] == [w.id for w in words[-3:]][::-1]


def test_review_session_ignores_the_order_of_new_words(
    client: TestClient, db_session: Session, words: list[Word]
):
    # Семь слов в обороте, а в занятие-повторение помещается пять:
    # берутся самые просроченные, и настройка на это не влияет
    started = [w.id for w in words[:7]]
    for word_id in started:
        client.post("/api/study/select", json={"word_id": word_id, "action": "learn"})
    for shift, word_id in enumerate(started):
        db_session.get(Progress, word_id).due_at = utcnow() - timedelta(hours=shift + 1)
    db_session.commit()

    def due() -> set[int]:
        return {e["word_id"] for e in _round_exercises(_session(client, "review")["rounds"])}

    before = due()
    _set_order(client, "newest_first")

    # FR-013: повторение идёт по сроку
    assert before == set(started[-5:])
    assert due() == before


def test_order_change_is_not_an_answer(client: TestClient, db_session: Session, words: list[Word]):
    _set_order(client, "newest_first")
    _set_order(client, "oldest_first")

    # FR-014
    assert db_session.scalars(select(ReviewLog)).all() == []


# ------------------------------------------------------------ «Учить первым»


def _raise(client: TestClient, word_id: int, priority: bool = True):
    return client.put(f"/api/words/{word_id}/priority", json={"priority": priority})


def test_priority_is_set_and_cleared(client: TestClient, words: list[Word]):
    word_id = words[3].id

    raised = _raise(client, word_id)
    assert raised.status_code == 200
    assert raised.json()["priority"] is True
    # Повтор того же значения — не ошибка
    assert _raise(client, word_id).status_code == 200

    lowered = _raise(client, word_id, False)
    assert lowered.status_code == 200
    assert lowered.json()["priority"] is False
    assert client.get(f"/api/words/{word_id}").json()["priority"] is False


def test_priority_of_a_missing_word_is_not_found(client: TestClient, words: list[Word]):
    assert _raise(client, 9999).status_code == 404


@pytest.mark.parametrize("order", ["oldest_first", "newest_first"])
def test_raised_words_come_first(client: TestClient, words: list[Word], order: str):
    _set_order(client, order)
    raised = {words[6].id, words[3].id, words[9].id}
    for word_id in raised:
        _raise(client, word_id)

    offered = [w["id"] for w in _session(client, "learn")["new_words"]]

    # FR-009, SC-002: сначала поднятые, затем остальные — внутри групп
    # действует выбранный порядок
    in_order = _ids_in_order(words, order)
    expected = [i for i in in_order if i in raised] + [i for i in in_order if i not in raised]
    assert offered == expected[:5]


def test_session_holds_only_raised_words_when_they_overflow(
    client: TestClient, words: list[Word]
):
    raised = [w.id for w in words[5:12]]
    for word_id in raised:
        _raise(client, word_id)

    offered = [w["id"] for w in _session(client, "learn")["new_words"]]

    assert offered == raised[:5]


def test_raised_words_do_not_bypass_the_daily_limit(
    client: TestClient, words: list[Word], monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings, "daily_new_limit", 9)
    for word in words[:7]:
        client.post("/api/study/select", json={"word_id": word.id, "action": "learn"})
    raised = [words[8].id, words[10].id, words[11].id]
    for word_id in raised:
        _raise(client, word_id)

    offered = [w["id"] for w in _session(client, "learn")["new_words"]]

    # FR-012: min(5, 9 − 7) = 2 слова, и оба — поднятые
    assert offered == raised[:2]


def test_replacement_prefers_a_raised_word(client: TestClient, words: list[Word]):
    shown = [w["id"] for w in _session(client, "learn")["new_words"]]
    _raise(client, words[10].id)

    body = client.post(
        "/api/study/select",
        json={"word_id": shown[0], "action": "know", "exclude_ids": shown},
    ).json()

    assert body["replacement"]["id"] == words[10].id


@pytest.mark.parametrize("action", ["learn", "know"])
def test_intro_choice_clears_the_priority(client: TestClient, words: list[Word], action: str):
    word_id = words[4].id
    _raise(client, word_id)

    client.post("/api/study/select", json={"word_id": word_id, "action": action})

    # FR-010: слово больше не новое, и отметка ему не нужна
    assert client.get(f"/api/words/{word_id}").json()["priority"] is False


def test_status_change_clears_the_priority(client: TestClient, words: list[Word]):
    word_id = words[4].id
    _raise(client, word_id)

    learning = client.put(f"/api/words/{word_id}/status", json={"status": WordStatus.LEARNING})
    assert learning.json()["priority"] is False

    # Возврат в «Новое» не возвращает отметку
    back = client.put(f"/api/words/{word_id}/status", json={"status": "new"})
    assert back.json()["progress"] is None
    assert back.json()["priority"] is False


def test_only_a_new_word_can_be_raised(client: TestClient, words: list[Word]):
    word_id = words[0].id
    client.post("/api/study/select", json={"word_id": word_id, "action": "learn"})

    # FR-008
    refused = _raise(client, word_id)
    assert refused.status_code == 409
    assert refused.json()["detail"]
    # Снять отметку можно всегда: запрос идемпотентен
    assert _raise(client, word_id, False).status_code == 200


def test_words_filter_by_priority(client: TestClient, words: list[Word]):
    for word in (words[0], words[1], words[7]):
        _raise(client, word.id)

    raised = client.get("/api/words", params={"priority": "true"}).json()
    assert {item["id"] for item in raised["items"]} == {words[0].id, words[1].id, words[7].id}
    assert all(item["priority"] for item in raised["items"])

    # FR-011: фильтр сочетается с поиском и со статусом
    searched = client.get("/api/words", params={"priority": "true", "search": "outsid"}).json()
    assert {item["word"] for item in searched["items"]} == {"outsider", "outside"}
    new_only = client.get("/api/words", params={"priority": "true", "status": "new"}).json()
    assert new_only["total"] == 3

    # Без фильтра — все слова
    assert client.get("/api/words").json()["total"] == len(words)


def test_priority_is_not_an_answer(client: TestClient, db_session: Session, words: list[Word]):
    _raise(client, words[2].id)
    _raise(client, words[2].id, False)

    # FR-014
    assert db_session.scalars(select(ReviewLog)).all() == []


# -------------------------------------------------------------------- метки


def _label(db_session: Session, name: str, *on: Word) -> Label:
    """Завести метку прямо в базе и навесить её на слова `on`."""
    label = Label(name=name, name_key=name.casefold())
    db_session.add(label)
    for word in on:
        word.labels.append(label)
    db_session.commit()
    return label


def _label_names(body: dict) -> list[str]:
    return [label["name"] for label in body["labels"]]


def _count(db_session: Session, table) -> int:
    return db_session.scalar(select(func.count()).select_from(table))


def test_labels_are_empty_on_a_fresh_dictionary(client: TestClient, words: list[Word]):
    assert client.get("/api/labels").json() == []
    # У слова без меток поле есть и пустое
    assert client.get(f"/api/words/{words[0].id}").json()["labels"] == []


def test_labels_are_listed_alphabetically_with_word_counts(
    client: TestClient, db_session: Session, words: list[Word]
):
    _label(db_session, "бета", words[0], words[1])
    _label(db_session, "Альфа", words[2])
    for name in ("ёлка", "ежевика", "ягода"):
        _label(db_session, name)

    body = client.get("/api/labels").json()

    # FR-009: без учёта регистра, «ё» между «е» и «ж», а не после «я»
    assert [label["name"] for label in body] == ["Альфа", "бета", "ежевика", "ёлка", "ягода"]
    assert [label["word_count"] for label in body] == [1, 2, 0, 0, 0]


def test_word_is_created_with_labels(client: TestClient, db_session: Session):
    created = client.post(
        "/api/words",
        json={"word": "knife", "translation": "нож", "labels": ["Посуда", "кухня"]},
    )

    assert created.status_code == 201, created.text
    # FR-001: метки в ответе сразу и по алфавиту
    assert _label_names(created.json()) == ["кухня", "Посуда"]
    kitchen_id = created.json()["labels"][0]["id"]

    # FR-004a: совпадение без учёта регистра берёт существующую метку с её написанием
    fork = client.post(
        "/api/words", json={"word": "fork", "translation": "вилка", "labels": ["КУХНЯ"]}
    ).json()
    assert fork["labels"] == [{"id": kitchen_id, "name": "кухня"}]
    assert _count(db_session, Label) == 2


def test_rejected_duplicate_leaves_no_new_label(client: TestClient, db_session: Session):
    client.post("/api/words", json={"word": "knife", "translation": "нож"})

    duplicate = client.post(
        "/api/words", json={"word": "knife", "translation": "нож", "labels": ["тест"]}
    )

    # FR-004a
    assert duplicate.status_code == 409
    assert db_session.scalar(select(Label).where(Label.name_key == "тест")) is None


def test_update_replaces_labels_only_when_asked(client: TestClient, words: list[Word]):
    word_id = words[0].id
    client.patch(f"/api/words/{word_id}", json={"labels": ["кухня"]})

    # FR-003a: без поля `labels` метки не меняются
    kept = client.patch(f"/api/words/{word_id}", json={"translation": "чужак"}).json()
    assert _label_names(kept) == ["кухня"]

    replaced = client.patch(f"/api/words/{word_id}", json={"labels": ["b", "a"]}).json()
    assert _label_names(replaced) == ["a", "b"]
    assert _label_names(client.get(f"/api/words/{word_id}").json()) == ["a", "b"]

    cleared = client.patch(f"/api/words/{word_id}", json={"labels": []}).json()
    assert cleared["labels"] == []


def test_rejected_update_keeps_the_labels(client: TestClient, db_session: Session):
    client.post("/api/words", json={"word": "roll out", "translation": "вылезать"})
    second = client.post(
        "/api/words",
        json={"word": "roll out", "translation": "внедрить", "labels": ["работа"]},
    ).json()

    clash = client.patch(
        f"/api/words/{second['id']}", json={"translation": "вылезать", "labels": ["новая"]}
    )

    # FR-003a
    assert clash.status_code == 409
    db_session.expire_all()
    assert _label_names(client.get(f"/api/words/{second['id']}").json()) == ["работа"]
    assert db_session.scalar(select(Label).where(Label.name_key == "новая")) is None


def test_repeated_label_names_collapse(client: TestClient, words: list[Word]):
    body = client.patch(
        f"/api/words/{words[0].id}", json={"labels": ["кухня", " КУХНЯ ", "кухня"]}
    ).json()

    # FR-002: первое вхождение побеждает
    assert _label_names(body) == ["кухня"]


@pytest.mark.parametrize("name", ["", "   ", "x" * 51])
def test_bad_label_name_is_rejected_on_a_word(client: TestClient, words: list[Word], name: str):
    created = client.post(
        "/api/words", json={"word": "spoon", "translation": "ложка", "labels": [name]}
    )
    updated = client.patch(f"/api/words/{words[0].id}", json={"labels": [name]})

    assert created.status_code == 422
    assert updated.status_code == 422


def test_labels_are_not_an_answer(client: TestClient, db_session: Session, words: list[Word]):
    word_id = words[0].id
    client.post("/api/study/select", json={"word_id": word_id, "action": "learn"})
    before = client.get(f"/api/words/{word_id}").json()["progress"]
    logged = _count(db_session, ReviewLog)

    client.patch(f"/api/words/{word_id}", json={"labels": ["кухня"]})
    after = client.patch(f"/api/words/{word_id}", json={"labels": []}).json()["progress"]

    # FR-005, SC-004
    for field in ("status", "ease", "lapses", "due_at"):
        assert after[field] == before[field]
    assert _count(db_session, ReviewLog) == logged


@pytest.mark.parametrize("status_value", ["new", WordStatus.KNOWN])
def test_status_change_keeps_the_labels(client: TestClient, words: list[Word], status_value):
    word_id = words[0].id
    client.patch(f"/api/words/{word_id}", json={"labels": ["кухня"]})
    client.post("/api/study/select", json={"word_id": word_id, "action": "learn"})

    body = client.put(f"/api/words/{word_id}/status", json={"status": status_value}).json()

    assert _label_names(body) == ["кухня"]


def test_deleting_a_word_keeps_its_labels(
    client: TestClient, db_session: Session, words: list[Word]
):
    word_id = words[0].id
    label = _label(db_session, "кухня", words[0])

    client.delete(f"/api/words/{word_id}")

    # FR-015
    links = select(func.count()).select_from(word_labels).where(word_labels.c.word_id == word_id)
    assert db_session.scalar(links) == 0
    assert [item["id"] for item in client.get("/api/labels").json()] == [label.id]


def _ids(client: TestClient, **params) -> set[int]:
    return {item["id"] for item in client.get("/api/words", params=params).json()["items"]}


def test_words_filter_by_label(client: TestClient, db_session: Session, words: list[Word]):
    kitchen = _label(db_session, "кухня", words[0], words[1], words[5])
    _label(db_session, "книга", words[1])
    labeled = {words[0].id, words[1].id, words[5].id}

    found = client.get("/api/words", params={"label": kitchen.id}).json()
    # FR-007
    assert {item["id"] for item in found["items"]} == labeled
    assert found["total"] == 3

    unlabeled = _ids(client, label="none", limit=200)
    assert unlabeled == {w.id for w in words} - labeled

    # FR-008: условия складываются
    assert _ids(client, label=kitchen.id, search="outsid") == {words[0].id, words[1].id}
    client.post("/api/study/select", json={"word_id": words[0].id, "action": "learn"})
    assert _ids(client, label=kitchen.id, status="new") == {words[1].id, words[5].id}
    _raise(client, words[5].id)
    assert _ids(client, label=kitchen.id, priority="true") == {words[5].id}


def test_words_filter_by_an_unknown_label(client: TestClient, words: list[Word]):
    assert client.get("/api/words", params={"label": 9999}).json()["total"] == 0
    assert client.get("/api/words", params={"label": "abc"}).status_code == 422


def test_removed_label_leaves_the_filter(
    client: TestClient, db_session: Session, words: list[Word]
):
    kitchen = _label(db_session, "кухня", words[0], words[1])

    client.patch(f"/api/words/{words[0].id}", json={"labels": []})

    assert _ids(client, label=kitchen.id) == {words[1].id}


def test_label_is_created(client: TestClient):
    created = client.post("/api/labels", json={"name": " кухня "})

    # FR-010
    assert created.status_code == 201, created.text
    assert created.json() == {
        "id": created.json()["id"],
        "name": "кухня",
        "description": None,
        "word_count": 0,
    }
    assert [label["name"] for label in client.get("/api/labels").json()] == ["кухня"]

    # FR-011: регистр не делает метку новой
    duplicate = client.post("/api/labels", json={"name": "КУХНЯ"})
    assert duplicate.status_code == 409
    assert "кухня" in duplicate.json()["detail"]


@pytest.mark.parametrize("name", ["", "   ", "x" * 51])
def test_bad_label_name_is_rejected(client: TestClient, db_session: Session, name: str):
    label = _label(db_session, "кухня")

    assert client.post("/api/labels", json={"name": name}).status_code == 422
    assert client.patch(f"/api/labels/{label.id}", json={"name": name}).status_code == 422


def test_label_is_renamed(client: TestClient, db_session: Session, words: list[Word]):
    kitchen = _label(db_session, "кухяня", words[0], words[1])
    _label(db_session, "Посуда")

    renamed = client.patch(f"/api/labels/{kitchen.id}", json={"name": "кухня"})

    # FR-012, SC-003: слова видят новое название, набор слов прежний
    assert renamed.status_code == 200, renamed.text
    assert renamed.json() == {
        "id": kitchen.id,
        "name": "кухня",
        "description": None,
        "word_count": 2,
    }
    for word in words[:2]:
        assert _label_names(client.get(f"/api/words/{word.id}").json()) == ["кухня"]

    # Занято другой меткой — конфликт, своё же название в другом регистре — нет
    assert client.patch(f"/api/labels/{kitchen.id}", json={"name": "посуда"}).status_code == 409
    own_case = client.patch(f"/api/labels/{kitchen.id}", json={"name": "Кухня"})
    assert own_case.status_code == 200
    assert own_case.json()["name"] == "Кухня"

    assert client.patch("/api/labels/9999", json={"name": "что-то"}).status_code == 404


def test_label_is_deleted(client: TestClient, db_session: Session, words: list[Word]):
    kitchen = _label(db_session, "кухня", words[0], words[1])
    client.post("/api/study/select", json={"word_id": words[0].id, "action": "learn"})
    counts = [_count(db_session, table) for table in (Word, Progress, ReviewLog)]

    assert client.delete(f"/api/labels/{kitchen.id}").status_code == 204
    # Связки ушли каскадом в базе; сессия теста общая с API и помнит старый список
    db_session.expire_all()

    # FR-014, SC-004: метка снята со слов, остальное не тронуто
    assert client.get("/api/labels").json() == []
    assert client.get(f"/api/words/{words[0].id}").json()["labels"] == []
    assert _count(db_session, word_labels) == 0
    assert [_count(db_session, table) for table in (Word, Progress, ReviewLog)] == counts

    assert client.delete(f"/api/labels/{kitchen.id}").status_code == 404


def test_labels_do_not_change_the_sessions(
    client: TestClient, db_session: Session, words: list[Word]
):
    _start(client, 3)
    _release(db_session, [w.id for w in words[:3]])

    def picked() -> tuple[list[int], set[int]]:
        learn = [w["id"] for w in _session(client, "learn")["new_words"]]
        review = {e["word_id"] for e in _round_exercises(_session(client, "review")["rounds"])}
        return learn, review

    before = picked()
    _label(db_session, "кухня", words[0], words[4], words[7])
    _label(db_session, "книга", words[3])

    # SC-006
    assert picked() == before


# -------------------------------------------------------- автоматическая разметка


class FakeClassifier:
    """Классификатор без сети: отвечает по таблице «слово → метка».

    Значение таблицы — название метки из набора, id любой метки (в том числе
    не из набора) или `None` — «ни одна». `during` вызывается «пока модель
    думает»: так тесты удаляют слово или метку посреди пачки.
    """

    def __init__(self) -> None:
        self.table: dict[str, str | int | None] = {}
        self.calls: list[tuple[list[WordItem], list[LabelItem]]] = []
        self.error: ClassifierError | None = None
        self.during: Callable[[], None] | None = None

    def classify(self, words: list[WordItem], labels: list[LabelItem]) -> dict[int, int | None]:
        self.calls.append((words, labels))
        if self.during is not None:
            self.during()
        if self.error is not None:
            raise self.error
        by_name = {label.name: label.id for label in labels}
        result: dict[int, int | None] = {}
        for word in words:
            choice = self.table.get(word.word)
            result[word.id] = by_name.get(choice) if isinstance(choice, str) else choice
        return result

    def check(self) -> None:
        if self.error is not None:
            raise self.error


@pytest.fixture
def fake(client: TestClient) -> FakeClassifier:
    classifier = FakeClassifier()
    app.dependency_overrides[get_classifier] = lambda: classifier
    return classifier


def _add_words(db_session: Session, *pairs: tuple[str, str]) -> list[Word]:
    now = utcnow()
    items = [Word(word=w, word_key=w, translation=t, created_at=now) for w, t in pairs]
    db_session.add_all(items)
    db_session.commit()
    return items


def _classify(client: TestClient, label_ids: list[int], **extra):
    payload = {"label_ids": label_ids, "limit": 20, **extra}
    return client.post("/api/labels/classify", json=payload)


def test_classify_puts_the_chosen_label(
    client: TestClient, db_session: Session, fake: FakeClassifier
):
    spoon, bicycle = _add_words(db_session, ("spoon", "ложка"), ("bicycle", "велосипед"))
    kitchen = _label(db_session, "кухня")
    body = _label(db_session, "тело")
    fake.table = {"spoon": "кухня", "bicycle": None}

    response = _classify(client, [kitchen.id, body.id])

    # FR-002, FR-003
    assert response.status_code == 200, response.text
    assert response.json() == {
        "results": [
            {
                "word_id": spoon.id,
                "word": "spoon",
                "translation": "ложка",
                "label": {"id": kitchen.id, "name": "кухня"},
                "added": True,
            },
            {
                "word_id": bicycle.id,
                "word": "bicycle",
                "translation": "велосипед",
                "label": None,
                "added": False,
            },
        ],
        "skipped": 0,
        "next_from_id": None,
        "remaining": 0,
    }
    assert _label_names(client.get(f"/api/words/{spoon.id}").json()) == ["кухня"]
    assert client.get(f"/api/words/{bicycle.id}").json()["labels"] == []

    # SC-003: повторный запуск ничего не меняет
    again = _classify(client, [kitchen.id, body.id]).json()
    assert [result["added"] for result in again["results"]] == [False, False]
    assert _count(db_session, word_labels) == 1


def test_classify_keeps_existing_labels(
    client: TestClient, db_session: Session, fake: FakeClassifier
):
    [spoon] = _add_words(db_session, ("spoon", "ложка"))
    kitchen = _label(db_session, "кухня", spoon)
    body = _label(db_session, "тело", spoon)
    fake.table = {"spoon": "кухня"}

    [result] = _classify(client, [kitchen.id, body.id]).json()["results"]

    # FR-004, SC-003: уже стоявшая метка не «добавлена», чужие не сняты
    assert result["label"] == {"id": kitchen.id, "name": "кухня"}
    assert result["added"] is False
    assert _label_names(client.get(f"/api/words/{spoon.id}").json()) == ["кухня", "тело"]
    assert _count(db_session, word_labels) == 2


def test_classify_ignores_a_label_outside_the_set(
    client: TestClient, db_session: Session, fake: FakeClassifier
):
    [spoon] = _add_words(db_session, ("spoon", "ложка"))
    kitchen = _label(db_session, "кухня")
    plants = _label(db_session, "растения")
    fake.table = {"spoon": plants.id}

    [result] = _classify(client, [kitchen.id]).json()["results"]

    # FR-014
    assert result["label"] is None
    assert result["added"] is False
    assert _count(db_session, word_labels) == 0


def test_classify_walks_the_dictionary_in_batches(
    client: TestClient, db_session: Session, words: list[Word], fake: FakeClassifier
):
    kitchen = _label(db_session, "кухня")
    sizes, remaining, seen = [], [], []
    from_id = None

    while True:
        batch = _classify(client, [kitchen.id], limit=5, from_id=from_id).json()
        sizes.append(len(batch["results"]))
        remaining.append(batch["remaining"])
        seen += [result["word_id"] for result in batch["results"]]
        from_id = batch["next_from_id"]
        if from_id is None:
            break

    # FR-011, R4
    assert sizes == [5, 5, 2]
    assert remaining == [7, 2, 0]
    assert seen == sorted(w.id for w in words)


@pytest.mark.parametrize("status_code", [502, 504])
def test_classifier_failure_leaves_the_batch_untouched(
    client: TestClient,
    db_session: Session,
    words: list[Word],
    fake: FakeClassifier,
    status_code: int,
):
    kitchen = _label(db_session, "кухня")
    fake.table = {w.word: "кухня" for w in words}
    fake.error = ClassifierError(status_code, "Сервис разметки недоступен")

    response = _classify(client, [kitchen.id])

    # FR-016, FR-018, SC-005
    assert response.status_code == status_code
    assert response.json() == {"detail": "Сервис разметки недоступен"}
    assert _count(db_session, word_labels) == 0


def test_word_deleted_during_classification_is_skipped(
    client: TestClient, db_session: Session, words: list[Word], fake: FakeClassifier
):
    kitchen = _label(db_session, "кухня")
    fake.table = {w.word: "кухня" for w in words}
    gone = words[1]

    def delete_word() -> None:
        db_session.delete(gone)
        db_session.commit()

    fake.during = delete_word

    response = _classify(client, [kitchen.id], limit=3)

    assert response.status_code == 200, response.text
    batch = response.json()
    assert batch["skipped"] == 1
    assert [result["word_id"] for result in batch["results"]] == [words[0].id, words[2].id]
    assert all(result["added"] for result in batch["results"])


def test_label_deleted_during_classification_is_not_put(
    client: TestClient, db_session: Session, words: list[Word], fake: FakeClassifier
):
    kitchen = _label(db_session, "кухня")
    body = _label(db_session, "тело")
    fake.table = {words[0].word: "кухня", words[1].word: "тело"}

    def delete_label() -> None:
        db_session.delete(kitchen)
        db_session.commit()

    fake.during = delete_label

    response = _classify(client, [kitchen.id, body.id], limit=2)

    assert response.status_code == 200, response.text
    first, second = response.json()["results"]
    assert first["label"] is None
    assert first["added"] is False
    assert second["label"] == {"id": body.id, "name": "тело"}
    assert second["added"] is True


@pytest.mark.parametrize(
    "payload",
    [
        {"label_ids": []},
        {"limit": 0},
        {"limit": settings.classifier_batch_max + 1},
        {"from_id": 0},
        {"status": "bogus"},
        {"label": "abc"},
    ],
)
def test_classify_rejects_bad_requests(
    client: TestClient, db_session: Session, words: list[Word], fake: FakeClassifier, payload
):
    kitchen = _label(db_session, "кухня")

    body = {"label_ids": [kitchen.id], "limit": 20, **payload}
    response = client.post("/api/labels/classify", json=body)

    # FR-010, FR-012
    assert response.status_code == 422
    assert fake.calls == []


def test_classify_needs_an_existing_label(
    client: TestClient, db_session: Session, words: list[Word], fake: FakeClassifier
):
    kitchen = _label(db_session, "кухня")
    client.delete(f"/api/labels/{kitchen.id}")

    response = _classify(client, [kitchen.id, 9999])

    # FR-010
    assert response.status_code == 422
    assert response.json() == {"detail": "Нет меток для разметки"}
    assert fake.calls == []


def test_classify_with_nothing_to_do(
    client: TestClient, db_session: Session, words: list[Word], fake: FakeClassifier
):
    kitchen = _label(db_session, "кухня")

    response = _classify(client, [kitchen.id], search="нет такого слова")

    assert response.status_code == 200
    assert response.json() == {"results": [], "skipped": 0, "next_from_id": None, "remaining": 0}
    assert fake.calls == []


def _snapshot(db_session: Session, model) -> list[tuple]:
    db_session.expire_all()
    columns = model.__table__.columns
    rows = db_session.scalars(select(model).order_by(*model.__table__.primary_key.columns))
    return [tuple(getattr(row, column.key) for column in columns) for row in rows]


def test_classification_is_not_an_answer(
    client: TestClient, db_session: Session, words: list[Word], fake: FakeClassifier
):
    kitchen = _label(db_session, "кухня")
    started = _start(client, 2)
    db_session.add(
        ReviewLog(
            word_id=started[0],
            exercise=ExerciseType.LETTERS,
            correct=True,
            status_before=WordStatus.LEARNING,
            status_after=WordStatus.LEARNING,
            ease_after=2.5,
            interval_after=0.0,
        )
    )
    db_session.commit()
    fake.table = {w.word: "кухня" for w in words}
    before = [_snapshot(db_session, model) for model in (Word, Progress, ReviewLog)]

    batch = _classify(client, [kitchen.id], limit=100).json()

    # FR-008, SC-004
    assert all(result["added"] for result in batch["results"])
    assert [_snapshot(db_session, model) for model in (Word, Progress, ReviewLog)] == before


def test_classifier_gets_label_descriptions(
    client: TestClient, db_session: Session, words: list[Word], fake: FakeClassifier
):
    kitchen = _label(db_session, "кухня")
    kitchen.description = "kitchen utensils and appliances"
    db_session.commit()
    body = _label(db_session, "тело")

    _classify(client, [kitchen.id, body.id], limit=1)

    # FR-007a
    [(sent_words, sent_labels)] = fake.calls
    first = words[0]
    assert sent_words == [WordItem(id=first.id, word=first.word, translation=first.translation)]
    assert {label.name: label.description for label in sent_labels} == {
        "кухня": "kitchen utensils and appliances",
        "тело": None,
    }


def test_words_from_id(client: TestClient, words: list[Word]):
    start = words[4].id

    page = client.get("/api/words", params={"from_id": start, "limit": 1}).json()

    # FR-013: курсор считает только записи с id ≥ from_id и складывается с фильтрами
    assert page["total"] == len(words) - 4
    assert page["items"][0]["id"] == start
    assert _ids(client, from_id=start, search="out") == {
        w.id for w in words[4:] if "out" in w.word
    }
    assert client.get("/api/words", params={"from_id": 0}).status_code == 422


def test_unlabeled_filter_does_not_shift_the_cursor(
    client: TestClient, db_session: Session, words: list[Word], fake: FakeClassifier
):
    kitchen = _label(db_session, "кухня")
    fake.table = {w.word: "кухня" for w in words}
    seen: list[int] = []
    from_id = None

    while True:
        batch = _classify(client, [kitchen.id], label="none", limit=5, from_id=from_id).json()
        seen += [result["word_id"] for result in batch["results"]]
        from_id = batch["next_from_id"]
        if from_id is None:
            break

    # R4: размеченные слова выпадают из «Без меток», но они позади курсора —
    # ни одно слово не пропущено и не обработано дважды
    assert seen == [w.id for w in words]
    assert _count(db_session, word_labels) == len(words)


@pytest.mark.parametrize(
    "params",
    [
        {"status": "new"},
        {"status": "learning"},
        {"search": "out"},
        {"priority": True},
        {"label": "none"},
        {"label": "kitchen"},
    ],
)
def test_classify_selects_what_the_dictionary_shows(
    client: TestClient, db_session: Session, words: list[Word], fake: FakeClassifier, params
):
    kitchen = _label(db_session, "кухня", words[0], words[3], words[8])
    _start(client, 3)
    _raise(client, words[10].id)
    _raise(client, words[11].id)
    if params.get("label") == "kitchen":
        params = {"label": kitchen.id}

    listed = [
        item["id"]
        for item in client.get("/api/words", params={**params, "limit": 200}).json()["items"]
    ]
    batch = _classify(client, [kitchen.id], limit=100, **params).json()

    # R3: разметка и список отбирают одни и те же слова
    assert listed
    assert [result["word_id"] for result in batch["results"]] == listed


# ------------------------------------------------- настройки классификатора


@pytest.fixture
def factory(client: TestClient):
    """Фабрика классификатора, запоминающая, с какими настройками её позвали."""

    class Factory:
        def __init__(self) -> None:
            self.fake = FakeClassifier()
            self.calls: list[tuple[ClassifierConfig, float]] = []

        def __call__(self, config: ClassifierConfig, timeout: float) -> FakeClassifier:
            self.calls.append((config, timeout))
            return self.fake

    made = Factory()
    app.dependency_overrides[get_classifier_factory] = lambda: made
    return made


DEFAULT_CLASSIFIER = {
    "base_url": settings.classifier_base_url,
    "api_key": settings.classifier_api_key,
    "model": settings.classifier_model,
}
CUSTOM_CLASSIFIER = {
    "base_url": "https://models.example.com",
    "api_key": "sk-123",
    "model": "bigger",
}


def _classifier_rows(db_session: Session) -> list[str]:
    db_session.expire_all()
    return list(db_session.scalars(select(Setting.key).where(Setting.key.like("classifier_%"))))


def test_classifier_settings_default_save_and_reset(client: TestClient, db_session: Session):
    # FR-020, FR-021
    assert client.get("/api/settings/classifier").json() == {
        **DEFAULT_CLASSIFIER,
        "is_default": True,
    }

    saved = client.put("/api/settings/classifier", json=CUSTOM_CLASSIFIER)
    assert saved.status_code == 200, saved.text
    assert saved.json() == {**CUSTOM_CLASSIFIER, "is_default": False}
    assert client.get("/api/settings/classifier").json() == {
        **CUSTOM_CLASSIFIER,
        "is_default": False,
    }

    # FR-022: сброс удаляет строки, а не записывает значения по умолчанию
    reset = client.delete("/api/settings/classifier")
    assert reset.status_code == 200
    assert reset.json() == {**DEFAULT_CLASSIFIER, "is_default": True}
    assert _classifier_rows(db_session) == []


def test_classifier_settings_are_trimmed(client: TestClient):
    payload = {"base_url": " http://localhost:11434 ", "api_key": " ollama ", "model": " nimble "}

    saved = client.put("/api/settings/classifier", json=payload).json()

    assert saved == {**DEFAULT_CLASSIFIER, "is_default": False}


@pytest.mark.parametrize(
    "change",
    [
        {"base_url": "ftp://x"},
        {"base_url": "localhost:11434"},
        {"base_url": "http://" + "x" * 506},
        {"model": ""},
        {"model": "   "},
        {"model": "m" * 129},
        {"api_key": ""},
        {"api_key": "with space"},
        {"api_key": "ключ"},
    ],
)
def test_bad_classifier_settings_are_rejected(
    client: TestClient, db_session: Session, factory, change: dict
):
    payload = {**CUSTOM_CLASSIFIER, **change}

    assert client.put("/api/settings/classifier", json=payload).status_code == 422
    assert client.post("/api/settings/classifier/check", json=payload).status_code == 422
    assert _classifier_rows(db_session) == []
    assert factory.calls == []


def test_classifier_check_uses_the_unsaved_values(client: TestClient, db_session: Session, factory):
    response = client.post("/api/settings/classifier/check", json=CUSTOM_CLASSIFIER)

    # FR-022: проверка не сохраняет и идёт с коротким таймаутом
    assert response.status_code == 200
    assert response.json() == {"ok": True, "detail": "Модель отвечает"}
    assert factory.calls == [
        (ClassifierConfig(**CUSTOM_CLASSIFIER), settings.classifier_check_timeout_seconds)
    ]
    assert _classifier_rows(db_session) == []


def test_classifier_check_reports_a_failure(client: TestClient, factory):
    factory.fake.error = ClassifierError(502, "Модель «nimbel» не найдена")

    response = client.post(
        "/api/settings/classifier/check", json={**CUSTOM_CLASSIFIER, "model": "nimbel"}
    )

    # Неудача проверки — ответ, а не ошибка запроса
    assert response.status_code == 200
    assert response.json() == {"ok": False, "detail": "Модель «nimbel» не найдена"}


def test_classify_uses_the_saved_settings(
    client: TestClient, db_session: Session, words: list[Word], factory, monkeypatch
):
    # SC-007: переменные окружения SDK ничего не перебивают
    monkeypatch.setenv("TYPESAFE_DEFAULT_MODEL", "other")
    monkeypatch.setenv("TYPESAFE_BASE_URL", "http://elsewhere.test")
    kitchen = _label(db_session, "кухня")
    client.put("/api/settings/classifier", json=CUSTOM_CLASSIFIER)

    _classify(client, [kitchen.id], limit=1)
    client.delete("/api/settings/classifier")
    _classify(client, [kitchen.id], limit=1)

    assert factory.calls == [
        (ClassifierConfig(**CUSTOM_CLASSIFIER), settings.classifier_timeout_seconds),
        (ClassifierConfig(**DEFAULT_CLASSIFIER), settings.classifier_timeout_seconds),
    ]


def test_label_description(client: TestClient, db_session: Session):
    created = client.post(
        "/api/labels", json={"name": "B2", "description": " advanced vocabulary (CEFR B2) "}
    )

    # FR-007a
    assert created.status_code == 201, created.text
    label_id = created.json()["id"]
    described = {
        "id": label_id,
        "name": "B2",
        "description": "advanced vocabulary (CEFR B2)",
        "word_count": 0,
    }
    assert created.json() == described
    assert client.get("/api/labels").json() == [described]

    # R9: переименование описание не трогает
    renamed = client.patch(f"/api/labels/{label_id}", json={"name": "C1"}).json()
    assert renamed["description"] == "advanced vocabulary (CEFR B2)"

    changed = client.patch(f"/api/labels/{label_id}", json={"description": "upper level"})
    assert changed.json() == {**described, "name": "C1", "description": "upper level"}

    # Пустое описание — его отсутствие
    cleared = client.patch(f"/api/labels/{label_id}", json={"description": "  "}).json()
    assert cleared["description"] is None
    assert cleared["name"] == "C1"
    assert client.patch(f"/api/labels/{label_id}", json={"description": None}).status_code == 200


def test_bad_label_description_is_rejected(client: TestClient, db_session: Session):
    label = _label(db_session, "кухня")

    too_long = {"description": "x" * 201}
    assert client.post("/api/labels", json={"name": "a", **too_long}).status_code == 422
    assert client.patch(f"/api/labels/{label.id}", json=too_long).status_code == 422
    # Частичное обновление без единого поля — ошибка, а не тихий успех
    assert client.patch(f"/api/labels/{label.id}", json={}).status_code == 422
