from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.clock import utcnow
from app.config import settings
from app.db import get_session
from app.models import Word
from app.routers.deps import get_word
from app.schemas import (
    AnswerRequest,
    AnswerResponse,
    ReviewFinishRequest,
    ReviewFinishResult,
    SelectRequest,
    SelectResponse,
    SessionMode,
    SessionOut,
    WordOut,
)
from app.study_service import (
    WordNotInStudyError,
    answer_exercise,
    build_session,
    fetch_new_words,
    finish_review_session,
    reset_word,
    select_word,
)

router = APIRouter(prefix="/study", tags=["study"])


@router.get("/session", response_model=SessionOut)
def get_session_queue(
    mode: SessionMode = Query(description="learn — новые слова, review — слова к повторению"),
    session: Session = Depends(get_session),
) -> SessionOut:
    """Набор занятия: новые слова на знакомство либо план раундов повторения."""
    return build_session(session, utcnow(), mode)


@router.get("/new", response_model=list[WordOut])
def get_new_words(
    limit: int | None = Query(default=None, ge=1, le=50),
    session: Session = Depends(get_session),
) -> list[Word]:
    return fetch_new_words(session, utcnow(), limit or settings.new_words_per_session)


@router.post("/select", response_model=SelectResponse)
def select(payload: SelectRequest, session: Session = Depends(get_session)) -> SelectResponse:
    """Экран знакомства: «Уже знаю» убирает слово из оборота, «Изучить» ставит в очередь."""
    word = session.get(Word, payload.word_id)
    if word is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Слово не найдено")
    return select_word(session, word, payload.action, utcnow(), payload.exclude_ids)


@router.post("/answer", response_model=AnswerResponse)
def answer(payload: AnswerRequest, session: Session = Depends(get_session)) -> AnswerResponse:
    word = session.get(Word, payload.word_id)
    if word is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Слово не найдено")
    try:
        return answer_exercise(session, word, payload, utcnow())
    except WordNotInStudyError:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="Слово ещё не взято в изучение"
        ) from None


@router.post("/review/finish", response_model=list[ReviewFinishResult])
def finish_review(
    payload: ReviewFinishRequest, session: Session = Depends(get_session)
) -> list[ReviewFinishResult]:
    """Конец занятия-повторения: расписание слов пересчитывается один раз.

    Неизвестный ключ занятия — не ошибка, а пустой список: занятие, в котором
    не было ни одного ответа, ничего не меняет.
    """
    return finish_review_session(session, payload.session_id, utcnow())


@router.post("/reset/{word_id}", status_code=status.HTTP_204_NO_CONTENT)
def reset(word: Word = Depends(get_word), session: Session = Depends(get_session)) -> Response:
    reset_word(session, word, utcnow())
    return Response(status_code=status.HTTP_204_NO_CONTENT)
