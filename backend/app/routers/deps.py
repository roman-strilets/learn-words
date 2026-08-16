from fastapi import Depends, HTTPException, Path, status
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Word


def get_word(
    word_id: int = Path(..., ge=1),
    session: Session = Depends(get_session),
) -> Word:
    word = session.get(Word, word_id)
    if word is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Слово не найдено")
    return word
