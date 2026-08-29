"""Сквозные проверки API: полный цикл изучения слова и работа со словарём."""

from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clock import utcnow
from app.models import ExerciseType, Progress, ReviewLog, Word, WordStatus
from app.srs import REVIEW_ROUNDS

LEARNING_CHAIN = [
    ExerciseType.CHOICE_RU_EN,
    ExerciseType.LETTERS,
    ExerciseType.DICTATION,
]


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


def _round_exercises(body: dict) -> list[dict]:
    """Все упражнения плана занятия подряд — когда порядок раундов не важен."""
    return [exercise for round_ in body["rounds"] for exercise in round_["exercises"]]


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
            for exercise in REVIEW_ROUNDS
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


def _finish(client: TestClient, session_id: str):
    response = client.post("/api/study/review/finish", json={"session_id": session_id})
    assert response.status_code == 200, response.text
    return response.json()


def _play_round(
    client: TestClient,
    session_id: str,
    round_: dict,
    answers: dict[int, dict[str, str]],
    wrong_for: int | None = None,
):
    """Пройти раунд целиком: верные ответы на все слова, кроме `wrong_for`.

    Ошибку тут же исправляем вторым показом — так занятие доходит до конца,
    как и требует FR-008.
    """
    exercise_type = round_["exercise"]
    for exercise in round_["exercises"]:
        word_id = exercise["word_id"]
        if word_id == wrong_for:
            _answer(
                client,
                word_id,
                exercise_type,
                "заведомо неверно",
                mode="review",
                session_id=session_id,
                attempt=1,
            )
        _answer(
            client,
            word_id,
            exercise_type,
            answers[word_id][exercise_type],
            mode="review",
            session_id=session_id,
            attempt=2 if word_id == wrong_for else 1,
        )


def test_health(client: TestClient):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_session_offers_new_words(client: TestClient, words: list[Word]):
    body = _session(client, "learn")

    assert len(body["new_words"]) == 5  # new_words_per_session
    assert body["rounds"] == []
    assert body["session_id"] is None
    assert body["counts"]["new"] == 5
    assert body["counts"]["in_study"] == 0


def test_full_learning_cycle(client: TestClient, db_session: Session, words: list[Word]):
    target = _first_new_word(client)
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
    target = _first_new_word(client)
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
    target = _first_new_word(client)
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
    target = _first_new_word(client)
    word_id = target["id"]

    body = client.post("/api/study/select", json={"word_id": word_id, "action": "know"}).json()
    assert body["progress"]["status"] == WordStatus.KNOWN
    assert body["next_exercise"] is None

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
    assert {e["word_id"] for e in _round_exercises(body)} == set(started)
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
        for exercise in _round_exercises(_session(client, "review"))
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

    assert len({e["word_id"] for e in _round_exercises(body)}) == 5  # review_words_per_session
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
    target = _first_new_word(client)
    word_id, spelling = target["id"], target["word"]
    client.post("/api/study/select", json={"word_id": word_id, "action": "learn"})
    _answer(client, word_id, ExerciseType.CHOICE_RU_EN, spelling)

    # Перезагрузка страницы = повторный запрос сессии; прогресс не теряется
    body = _session(client, "review")
    pending = [e for e in _round_exercises(body) if e["word_id"] == word_id]
    # Слово ждёт в каждом раунде: занятие пересобирается целиком
    assert [e["type"] for e in pending] == list(REVIEW_ROUNDS)
    assert body["counts"]["learning"] == 1


def test_answer_for_word_not_in_study_is_rejected(client: TestClient, words: list[Word]):
    response = client.post(
        "/api/study/answer",
        json={"word_id": words[0].id, "exercise": ExerciseType.DICTATION, "answer": "x"},
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
    assert word_id not in {e["word_id"] for e in _round_exercises(_session(client, "review"))}


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
    assert [r["exercise"] for r in body["rounds"]] == list(REVIEW_ROUNDS)
    for round_ in body["rounds"]:
        # В раунде — по одному упражнению своего типа на каждое слово занятия
        assert {e["word_id"] for e in round_["exercises"]} == set(started)
        assert {e["type"] for e in round_["exercises"]} == {round_["exercise"]}


def test_review_session_is_empty_without_due_words(client: TestClient, words: list[Word]):
    body = _session(client, "review")

    assert body["rounds"] == []
    assert body["session_id"] is None


def test_review_plan_holds_four_exercises_per_word(client: TestClient, words: list[Word]):
    started = _start(client)

    body = _session(client, "review")
    exercises = _round_exercises(body)

    # SC-001, SC-002: занятие — это «слов × 4», сгруппированных по типу
    assert len(exercises) == len(started) * len(REVIEW_ROUNDS)
    assert [r["exercise"] for r in body["rounds"]] == list(REVIEW_ROUNDS)


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
        REVIEW_ROUNDS[0],
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
    assert logged[0].exercise == REVIEW_ROUNDS[0]
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


def test_review_answer_without_session_id_is_rejected(client: TestClient, words: list[Word]):
    word_id = _start(client, 1)[0]

    response = client.post(
        "/api/study/answer",
        json={
            "word_id": word_id,
            "exercise": REVIEW_ROUNDS[0],
            "answer": "x",
            "mode": "review",
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
