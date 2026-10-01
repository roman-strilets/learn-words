from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.classifier import (
    ClassifierConfig,
    ClassifierError,
    ClassifierFactory,
    get_classifier_factory,
    load_classifier_config,
    reset_classifier_config,
    save_classifier_config,
)
from app.config import settings as app_settings
from app.db import get_session
from app.schemas import AppSettings, ClassifierCheck, ClassifierInput, ClassifierSettings
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


def _classifier_settings(session: Session) -> ClassifierSettings:
    config, is_default = load_classifier_config(session)
    return ClassifierSettings(
        base_url=config.base_url,
        api_key=config.api_key,
        model=config.model,
        is_default=is_default,
    )


def _config(payload: ClassifierInput) -> ClassifierConfig:
    return ClassifierConfig(base_url=payload.base_url, api_key=payload.api_key, model=payload.model)


@router.get("/classifier", response_model=ClassifierSettings)
def get_classifier_settings(session: Session = Depends(get_session)) -> ClassifierSettings:
    """Действующее подключение к классификатору меток."""
    return _classifier_settings(session)


@router.put("/classifier", response_model=ClassifierSettings)
def update_classifier_settings(
    payload: ClassifierInput, session: Session = Depends(get_session)
) -> ClassifierSettings:
    """Сохранить подключение. Не проверяет его: сервис может быть сейчас выключен."""
    save_classifier_config(session, _config(payload))
    return _classifier_settings(session)


@router.delete("/classifier", response_model=ClassifierSettings)
def reset_classifier_settings(session: Session = Depends(get_session)) -> ClassifierSettings:
    """Забыть сохранённое подключение и вернуть значения по умолчанию."""
    reset_classifier_config(session)
    return _classifier_settings(session)


@router.post("/classifier/check", response_model=ClassifierCheck)
def check_classifier(
    payload: ClassifierInput,
    factory: ClassifierFactory = Depends(get_classifier_factory),
) -> ClassifierCheck:
    """Проверить переданные — не обязательно сохранённые — значения одним вопросом модели.

    Обычный `def`: ожидание модели идёт в пуле потоков.
    """
    classifier = factory(_config(payload), app_settings.classifier_check_timeout_seconds)
    try:
        classifier.check()
    except ClassifierError as err:
        return ClassifierCheck(ok=False, detail=err.detail)
    return ClassifierCheck(ok=True, detail="Модель отвечает")
