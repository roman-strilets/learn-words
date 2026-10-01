from fastapi import APIRouter, Depends, HTTPException, Path, Response, status
from sqlalchemy.orm import Session

from app.classifier import Classifier, ClassifierError, get_classifier
from app.db import get_session
from app.labels_service import (
    NoLabelsError,
    classify_batch,
    find_by_key,
    label_key,
    label_out,
    list_labels,
    word_count,
)
from app.models import Label
from app.schemas import ClassifyBatch, ClassifyRequest, LabelInput, LabelOut, LabelUpdate
from app.word_filters import WordFilterError

router = APIRouter(prefix="/labels", tags=["labels"])


def _get_label(
    label_id: int = Path(..., ge=1), session: Session = Depends(get_session)
) -> Label:
    label = session.get(Label, label_id)
    if label is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Метка не найдена")
    return label


def _taken(existing: Label) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, detail=f"Метка «{existing.name}» уже есть")


@router.get("", response_model=list[LabelOut])
def get_labels(session: Session = Depends(get_session)) -> list[LabelOut]:
    return list_labels(session)


@router.post("", response_model=LabelOut, status_code=status.HTTP_201_CREATED)
def create_label(payload: LabelInput, session: Session = Depends(get_session)) -> LabelOut:
    key = label_key(payload.name)
    existing = find_by_key(session, key)
    if existing is not None:
        raise _taken(existing)

    label = Label(name=payload.name, name_key=key, description=payload.description)
    session.add(label)
    session.flush()
    return label_out(label, 0)


@router.post("/classify", response_model=ClassifyBatch)
def classify(
    payload: ClassifyRequest,
    session: Session = Depends(get_session),
    classifier: Classifier = Depends(get_classifier),
) -> ClassifyBatch:
    """Разметить одну пачку слов автоматически.

    Обычный `def`: FastAPI выполнит его в пуле потоков, и минута ожидания
    модели не блокирует другие запросы.
    """
    try:
        return classify_batch(session, payload, classifier)
    except (WordFilterError, NoLabelsError) as err:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(err)) from None
    except ClassifierError as err:
        raise HTTPException(err.status_code, detail=err.detail) from None


@router.patch("/{label_id}", response_model=LabelOut)
def update_label(
    payload: LabelUpdate,
    label: Label = Depends(_get_label),
    session: Session = Depends(get_session),
) -> LabelOut:
    """Переименовать метку или поменять описание — только переданные поля.

    Смена только регистра своего же названия — не конфликт.
    """
    if "name" in payload.model_fields_set and payload.name is not None:
        key = label_key(payload.name)
        clash = find_by_key(session, key, exclude_id=label.id)
        if clash is not None:
            raise _taken(clash)
        label.name = payload.name
        label.name_key = key
    if "description" in payload.model_fields_set:
        label.description = payload.description

    session.flush()
    return label_out(label, word_count(session, label))


@router.delete("/{label_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_label(
    label: Label = Depends(_get_label), session: Session = Depends(get_session)
) -> Response:
    """Удалить метку. Связки со словами уходят каскадом, сами слова не меняются."""
    session.delete(label)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
