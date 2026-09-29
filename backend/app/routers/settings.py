from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_session
from app.schemas import AppSettings
from app.study_service import get_new_words_order, set_new_words_order

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=AppSettings)
def get_settings(session: Session = Depends(get_session)) -> AppSettings:
    return AppSettings(new_words_order=get_new_words_order(session))


@router.put("", response_model=AppSettings)
def update_settings(
    payload: AppSettings, session: Session = Depends(get_session)
) -> AppSettings:
    """Сохранить настройки. Ответом на упражнение это не считается."""
    set_new_words_order(session, payload.new_words_order)
    return payload
