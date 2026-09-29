from fastapi import APIRouter, Depends, HTTPException, Path, Response, status
from sqlalchemy.orm import Session

from app.db import get_session
from app.labels_service import find_by_key, label_key, list_labels, word_count
from app.models import Label
from app.schemas import LabelInput, LabelOut

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

    label = Label(name=payload.name, name_key=key)
    session.add(label)
    session.flush()
    return LabelOut(id=label.id, name=label.name, word_count=0)


@router.patch("/{label_id}", response_model=LabelOut)
def rename_label(
    payload: LabelInput,
    label: Label = Depends(_get_label),
    session: Session = Depends(get_session),
) -> LabelOut:
    """Переименовать метку. Смена только регистра своего же названия — не конфликт."""
    key = label_key(payload.name)
    clash = find_by_key(session, key, exclude_id=label.id)
    if clash is not None:
        raise _taken(clash)

    label.name = payload.name
    label.name_key = key
    session.flush()
    return LabelOut(id=label.id, name=label.name, word_count=word_count(session, label))


@router.delete("/{label_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_label(
    label: Label = Depends(_get_label), session: Session = Depends(get_session)
) -> Response:
    """Удалить метку. Связки со словами уходят каскадом, сами слова не меняются."""
    session.delete(label)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
