"""Занятие по группе — `/group-study`: порция слов одной метки, пять раундов.

Тонкий роутер над `group_study_service`: найти метку и слово, отдать 404/409,
вызвать сервис.
"""

from fastapi import APIRouter, Depends, HTTPException, Path, Response, status
from sqlalchemy.orm import Session

from app.clock import utcnow
from app.db import get_session
from app.group_study_service import (
    WordNotInGroupError,
    answer_group_exercise,
    build_group_session,
    finish_group_session,
    list_groups,
    restart_group,
)
from app.models import Label, Word
from app.schemas import (
    GroupAnswerRequest,
    GroupAnswerResponse,
    GroupFinishRequest,
    GroupFinishResult,
    GroupOut,
    GroupSessionOut,
    GroupSessionRequest,
)

router = APIRouter(prefix="/group-study", tags=["group-study"])


def _label(session: Session, label_id: int) -> Label:
    label = session.get(Label, label_id)
    if label is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Метка не найдена")
    return label


@router.get("/groups", response_model=list[GroupOut])
def groups(session: Session = Depends(get_session)) -> list[GroupOut]:
    """Все метки слов с размером группы и местом в круге. Ничего не создаёт."""
    return list_groups(session)


@router.post("/session", response_model=GroupSessionOut)
def group_session(
    payload: GroupSessionRequest, session: Session = Depends(get_session)
) -> GroupSessionOut:
    """Порция группы. `POST`: сборка заводит строки круга (research R7)."""
    return build_group_session(session, _label(session, payload.label_id), utcnow())


@router.post("/answer", response_model=GroupAnswerResponse)
def answer(
    payload: GroupAnswerRequest, session: Session = Depends(get_session)
) -> GroupAnswerResponse:
    label = _label(session, payload.label_id)
    word = session.get(Word, payload.word_id)
    if word is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Слово не найдено")
    try:
        return answer_group_exercise(session, word, label, payload, utcnow())
    except WordNotInGroupError:
        # Метку сняли посреди занятия: фронт уберёт слово из оставшихся раундов
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="Слова больше нет в группе"
        ) from None


@router.post("/finish", response_model=list[GroupFinishResult])
def finish(
    payload: GroupFinishRequest, session: Session = Depends(get_session)
) -> list[GroupFinishResult]:
    """Отметить пройденными слова порции. Неизвестный ключ — пустой список."""
    return finish_group_session(session, payload.session_id, utcnow())


@router.post("/groups/{label_id}/restart", status_code=status.HTTP_204_NO_CONTENT)
def restart(
    label_id: int = Path(..., ge=1), session: Session = Depends(get_session)
) -> Response:
    """Начать круг группы заново. Прогресс слов не меняется."""
    restart_group(session, _label(session, label_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
