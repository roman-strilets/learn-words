"""Занятие колоды: слова — `/study`, фразы — `/phrase-study`.

Один и тот же набор маршрутов над одним `study_service`: колода решает,
из каких таблиц брать записи и куда писать журнал.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.clock import utcnow
from app.db import get_session
from app.decks import PHRASES, WORDS, Deck
from app.models import Phrase, Word
from app.routers.deps import get_item
from app.schemas import (
    AnswerRequest,
    AnswerResponse,
    ExerciseRound,
    RoundsRequest,
    SelectRequest,
    SelectResponse,
    SessionFinishRequest,
    SessionFinishResult,
    SessionMode,
    SessionOut,
    WordOut,
)
from app.study_service import (
    WordNotInStudyError,
    answer_exercise,
    build_rounds,
    build_session,
    fetch_new_words,
    finish_session,
    reset_word,
    select_word,
)


def make_study_router(deck: Deck, prefix: str) -> APIRouter:
    router = APIRouter(prefix=prefix, tags=[f"{deck.name}-study"])
    get_word = get_item(deck)

    def _find(session: Session, word_id: int) -> Word | Phrase:
        word = session.get(deck.item, word_id)
        if word is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=deck.not_found)
        return word

    @router.get("/session", response_model=SessionOut)
    def get_session_queue(
        mode: SessionMode = Query(description="learn — новые записи, review — к повторению"),
        session: Session = Depends(get_session),
    ) -> SessionOut:
        """Набор занятия: новые записи на знакомство либо план раундов повторения."""
        return build_session(session, utcnow(), mode, deck=deck)

    @router.post("/rounds", response_model=list[ExerciseRound])
    def rounds(
        payload: RoundsRequest, session: Session = Depends(get_session)
    ) -> list[ExerciseRound]:
        """План раундов по записям, взятым в изучение по итогам знакомства.

        Пустой список — не ошибка: все записи занятия могли оказаться
        знакомыми. Запись, выбывшая из оборота между знакомством и запросом,
        молча пропускается — занятие идёт дальше на остальных.
        """
        return build_rounds(session, payload.word_ids, deck=deck)

    @router.get("/new", response_model=list[WordOut])
    def get_new_words(
        limit: int | None = Query(default=None, ge=1, le=50),
        session: Session = Depends(get_session),
    ) -> list[Word | Phrase]:
        return fetch_new_words(session, utcnow(), limit or deck.new_per_session, deck=deck)

    @router.post("/select", response_model=SelectResponse)
    def select(
        payload: SelectRequest, session: Session = Depends(get_session)
    ) -> SelectResponse:
        """Экран знакомства: «Уже знаю» убирает запись из оборота, «Изучить» ставит в очередь."""
        word = _find(session, payload.word_id)
        return select_word(
            session, word, payload.action, utcnow(), payload.exclude_ids, deck=deck
        )

    @router.post("/answer", response_model=AnswerResponse)
    def answer(
        payload: AnswerRequest, session: Session = Depends(get_session)
    ) -> AnswerResponse:
        word = _find(session, payload.word_id)
        try:
            return answer_exercise(session, word, payload, utcnow(), deck=deck)
        except WordNotInStudyError:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail="Слово ещё не взято в изучение"
                if deck is WORDS
                else "Фраза ещё не взята в изучение",
            ) from None

    @router.post("/finish", response_model=list[SessionFinishResult])
    def finish(
        payload: SessionFinishRequest, session: Session = Depends(get_session)
    ) -> list[SessionFinishResult]:
        """Конец занятия: расписание записей пересчитывается один раз.

        Неизвестный ключ занятия — не ошибка, а пустой список: занятие, в котором
        не было ни одного ответа, ничего не меняет. Ключ занятия другой колоды
        тоже неизвестен — журналы у колод разные.
        """
        return finish_session(session, payload.session_id, payload.mode, utcnow(), deck=deck)

    @router.post("/reset/{word_id}", status_code=status.HTTP_204_NO_CONTENT)
    def reset(
        word: Word | Phrase = Depends(get_word), session: Session = Depends(get_session)
    ) -> Response:
        reset_word(session, word, utcnow())
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router


router = make_study_router(WORDS, "/study")
phrase_study_router = make_study_router(PHRASES, "/phrase-study")
