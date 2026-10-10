from collections.abc import Callable

from fastapi import Depends, HTTPException, Path, status
from sqlalchemy.orm import Session

from app.db import get_session
from app.decks import WORDS, Deck
from app.models import Phrase, Word


def get_item(deck: Deck) -> Callable[..., Word | Phrase]:
    """Зависимость «запись колоды по `word_id` из пути или 404».

    Параметр пути и у фраз называется `word_id`: роутеры колод строятся одной
    фабрикой, а в OpenAPI это только имя.
    """

    def dependency(
        word_id: int = Path(..., ge=1),
        session: Session = Depends(get_session),
    ) -> Word | Phrase:
        item = session.get(deck.item, word_id)
        if item is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail=deck.not_found)
        return item

    return dependency


get_word = get_item(WORDS)
