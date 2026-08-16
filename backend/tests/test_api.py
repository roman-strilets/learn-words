"""Сквозные проверки API: полный цикл изучения слова и работа со словарём."""

from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clock import utcnow
from app.models import ExerciseType, Progress, ReviewLog, Word, WordStatus

LEARNING_CHAIN = [
    ExerciseType.CHOICE_RU_EN,
    ExerciseType.LETTERS,
    ExerciseType.DICTATION,
]


def _answer(client: TestClient, word_id: int, exercise: str, answer: str, **extra):
    payload = {"word_id": word_id, "exercise": exercise, "answer": answer, **extra}
    response = client.post("/api/study/answer", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def test_health(client: TestClient):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_session_offers_new_words(client: TestClient, words: list[Word]):
    body = client.get("/api/study/session").json()

    assert len(body["new_words"]) == 5  # new_words_per_session
    assert body["exercises"] == []
    assert body["counts"]["new"] == 5
    assert body["counts"]["in_study"] == 0


def test_full_learning_cycle(client: TestClient, db_session: Session, words: list[Word]):
    target = client.get("/api/study/session").json()["new_words"][0]
    word_id, spelling = target["id"], target["word"]

    # Экран знакомства: «Изучить» засчитывает карточку и выдаёт первое упражнение
    selected = client.post(
        "/api/study/select", json={"word_id": word_id, "action": "learn"}
    ).json()
    assert selected["progress"]["status"] == WordStatus.LEARNING
    assert selected["next_exercise"]["type"] == ExerciseType.CHOICE_RU_EN

    exercise = selected["next_exercise"]
    for expected_next in LEARNING_CHAIN[1:]:
        result = _answer(client, word_id, exercise["type"], spelling)
        assert result["correct"] is True
        assert result["repeat_in_session"] is True
        assert result["next_exercise"]["type"] == expected_next
        exercise = result["next_exercise"]

    # Последний шаг — выпуск в режим повторений
    result = _answer(client, word_id, ExerciseType.DICTATION, spelling)
    assert result["correct"] is True
    assert result["repeat_in_session"] is False
    assert result["next_exercise"] is None
    assert result["progress"]["status"] == WordStatus.REVIEW
    assert result["progress"]["repetitions"] == 1
    assert result["progress"]["interval_days"] == 1.0

    progress = db_session.get(Progress, word_id)
    assert timedelta(hours=20) < progress.due_at - utcnow() < timedelta(hours=28)

    logs = db_session.scalars(select(ReviewLog).where(ReviewLog.word_id == word_id)).all()
    assert [log.exercise for log in logs] == [ExerciseType.INTRO] + LEARNING_CHAIN
    assert all(log.correct for log in logs)


def test_wrong_answer_steps_back_and_repeats(client: TestClient, words: list[Word]):
    target = client.get("/api/study/session").json()["new_words"][0]
    word_id, spelling = target["id"], target["word"]

    client.post("/api/study/select", json={"word_id": word_id, "action": "learn"})
    _answer(client, word_id, ExerciseType.CHOICE_RU_EN, spelling)

    result = _answer(client, word_id, ExerciseType.LETTERS, "заведомо неверно")

    assert result["correct"] is False
    assert result["correct_answer"] == spelling
    assert result["quality"] == 2
    assert result["repeat_in_session"] is True
    assert result["next_exercise"]["type"] == ExerciseType.CHOICE_RU_EN
    assert result["progress"]["step"] == 1


def test_hint_lowers_quality(client: TestClient, words: list[Word]):
    target = client.get("/api/study/session").json()["new_words"][0]
    word_id, spelling = target["id"], target["word"]
    client.post("/api/study/select", json={"word_id": word_id, "action": "learn"})

    result = _answer(
        client, word_id, ExerciseType.CHOICE_RU_EN, spelling, used_hint=True
    )
    assert result["correct"] is True
    assert result["quality"] == 4


def test_already_known_word_leaves_rotation(
    client: TestClient, db_session: Session, words: list[Word]
):
    target = client.get("/api/study/session").json()["new_words"][0]
    word_id = target["id"]

    body = client.post("/api/study/select", json={"word_id": word_id, "action": "know"}).json()
    assert body["progress"]["status"] == WordStatus.KNOWN
    assert body["next_exercise"] is None

    offered = {w["id"] for w in client.get("/api/study/session").json()["new_words"]}
    assert word_id not in offered


def test_session_rebuilds_after_reload(client: TestClient, words: list[Word]):
    target = client.get("/api/study/session").json()["new_words"][0]
    word_id, spelling = target["id"], target["word"]
    client.post("/api/study/select", json={"word_id": word_id, "action": "learn"})
    _answer(client, word_id, ExerciseType.CHOICE_RU_EN, spelling)

    # Перезагрузка страницы = повторный запрос сессии; прогресс не теряется
    body = client.get("/api/study/session").json()
    pending = [e for e in body["exercises"] if e["word_id"] == word_id]
    assert len(pending) == 1
    assert pending[0]["type"] == ExerciseType.LETTERS
    assert body["counts"]["learning"] == 1


def test_answer_for_word_not_in_study_is_rejected(client: TestClient, words: list[Word]):
    response = client.post(
        "/api/study/answer",
        json={"word_id": words[0].id, "exercise": ExerciseType.DICTATION, "answer": "x"},
    )
    assert response.status_code == 409


def test_reset_returns_word_to_new(client: TestClient, words: list[Word]):
    word_id = client.get("/api/study/session").json()["new_words"][0]["id"]
    client.post("/api/study/select", json={"word_id": word_id, "action": "learn"})

    assert client.post(f"/api/study/reset/{word_id}").status_code == 204
    assert client.get(f"/api/words/{word_id}").json()["progress"] is None


def test_create_word_and_reject_duplicate(client: TestClient):
    created = client.post(
        "/api/words",
        json={"word": " Serendipity ", "translation": "счастливая случайность"},
    )
    assert created.status_code == 201
    assert created.json()["word"] == "Serendipity"

    duplicate = client.post(
        "/api/words", json={"word": "serendipity", "translation": "другое значение"}
    )
    assert duplicate.status_code == 409
    assert "уже есть" in duplicate.json()["detail"]


def test_new_word_is_offered_for_study(client: TestClient, db_session: Session):
    created = client.post(
        "/api/words", json={"word": "quirk", "translation": "причуда"}
    ).json()

    offered = {w["id"] for w in client.get("/api/study/session").json()["new_words"]}
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
    word_id = client.get("/api/study/session").json()["new_words"][0]["id"]
    client.post("/api/study/select", json={"word_id": word_id, "action": "learn"})

    client.delete(f"/api/words/{word_id}")
    db_session.expire_all()
    assert db_session.get(Progress, word_id) is None


def test_words_search_and_status_filter(client: TestClient, words: list[Word]):
    # «outsid» — подстрока и outsider, и outside
    prefix = client.get("/api/words", params={"search": "outsid"}).json()
    assert {item["word"] for item in prefix["items"]} == {"outsider", "outside"}

    found = client.get("/api/words", params={"search": "outsider"}).json()
    assert found["total"] == 1
    assert found["items"][0]["word"] == "outsider"

    by_translation = client.get("/api/words", params={"search": "край"}).json()
    assert by_translation["total"] == 1

    word_id = client.get("/api/study/session").json()["new_words"][0]["id"]
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

    word_id = client.get("/api/study/session").json()["new_words"][0]["id"]
    client.post("/api/study/select", json={"word_id": word_id, "action": "learn"})

    after = client.get("/api/stats/overview").json()
    assert after["learning"] == 1
    assert after["new"] == len(words) - 1
    assert after["answers_today"] == 1
    assert after["new_today"] == 1
    assert after["streak_days"] == 1
    assert after["due_now"] == 1


def test_stats_daily_covers_requested_window(client: TestClient, words: list[Word]):
    word_id = client.get("/api/study/session").json()["new_words"][0]["id"]
    client.post("/api/study/select", json={"word_id": word_id, "action": "learn"})

    daily = client.get("/api/stats/daily", params={"days": 7}).json()
    assert len(daily) == 7
    assert daily[-1]["date"] == utcnow().date().isoformat()
    assert daily[-1]["answers"] == 1
    assert daily[-1]["correct"] == 1
    assert daily[-1]["accuracy"] == 1.0
    assert daily[-1]["new_words"] == 1
