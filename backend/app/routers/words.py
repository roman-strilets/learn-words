"""Словарь колоды: список с фильтрами, добавление, правка, статус, отметка.

Роутер строится фабрикой: слова живут под `/words`, фразы — под `/phrases`,
код и схемы ответов общие (research R3).
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clock import utcnow
from app.db import get_session
from app.decks import PHRASES, WORDS, Deck
from app.exercises import translation_variants, word_key_for
from app.labels_service import resolve_labels
from app.models import Phrase, Word
from app.routers.deps import get_item
from app.schemas import (
    PhraseCreate,
    PhraseUpdate,
    WordCreate,
    WordOut,
    WordPage,
    WordPriorityUpdate,
    WordStatusUpdate,
    WordUpdate,
    WordWithProgress,
)
from app.study_service import WordNotNewError, set_word_priority, set_word_status
from app.word_filters import WordFilterError, count_rows, filtered_words


def _same_meaning(
    session: Session, deck: Deck, key: str, translation: str, *, exclude_id: int | None = None
) -> Word | Phrase | None:
    """Запись колоды с тем же текстом и тем же значением.

    Слово можно завести ещё раз ради другого значения, поэтому дубль ищется
    по паре: совпал ключ слова и хотя бы одно значение перевода.
    """
    Item = deck.item
    stmt = select(Item).where(Item.word_key == key)
    if exclude_id is not None:
        stmt = stmt.where(Item.id != exclude_id)
    variants = translation_variants(translation)
    return next(
        (w for w in session.scalars(stmt) if translation_variants(w.translation) & variants),
        None,
    )


def make_words_router(
    deck: Deck,
    prefix: str,
    create_schema: type[WordCreate],
    update_schema: type[WordUpdate],
) -> APIRouter:
    router = APIRouter(prefix=prefix, tags=[deck.name])
    get_word = get_item(deck)
    # Курсор `from_id` нужен только автоматической разметке, а она есть лишь у слов
    with_cursor = deck is WORDS

    def _duplicate(existing: Word | Phrase) -> HTTPException:
        return HTTPException(
            status.HTTP_409_CONFLICT,
            detail=deck.duplicate_detail(existing.word, existing.translation),
        )

    @router.get("", response_model=WordPage)
    def list_words(
        search: str | None = Query(default=None, description="Подстрока в тексте или переводе"),
        status_filter: str | None = Query(
            default=None,
            alias="status",
            description="new | learning | review | known | suspended",
        ),
        priority: bool | None = Query(
            default=None, description="Только записи с отметкой «Учить первым»"
        ),
        # Одно значение вместо пары `label_id` + `unlabeled`: противоречие не передать
        label: str | None = Query(
            default=None, description="id метки или none — записи без меток"
        ),
        from_id: int | None = Query(
            default=None,
            ge=1,
            description="Только записи с id ≥ from_id — курсор разметки",
            include_in_schema=with_cursor,
        ),
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        session: Session = Depends(get_session),
    ) -> WordPage:
        try:
            stmt = filtered_words(
                search=search,
                status=status_filter,
                priority=priority,
                label=label,
                from_id=from_id if with_cursor else None,
                deck=deck,
            )
        except WordFilterError as err:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(err)) from None

        total = session.scalar(count_rows(stmt)) or 0
        items = session.scalars(stmt.order_by(deck.item.id).limit(limit).offset(offset)).all()

        return WordPage(
            items=[WordWithProgress.model_validate(w) for w in items],
            total=total,
            limit=limit,
            offset=offset,
        )

    @router.post("", response_model=WordOut, status_code=status.HTTP_201_CREATED)
    def create_word(
        payload: create_schema,  # type: ignore[valid-type]
        session: Session = Depends(get_session),
    ) -> Word | Phrase:
        key = word_key_for(payload.word)
        existing = _same_meaning(session, deck, key, payload.translation)
        if existing is not None:
            raise _duplicate(existing)

        word = deck.item(
            word=payload.word,
            word_key=key,
            translation=payload.translation,
            example=payload.example,
            example_translation=payload.example_translation,
            created_at=utcnow(),
        )
        word.labels = resolve_labels(session, payload.labels, deck)
        session.add(word)
        session.flush()
        return word

    @router.get("/{word_id}", response_model=WordWithProgress)
    def get_word_detail(word: Word | Phrase = Depends(get_word)) -> Word | Phrase:
        return word

    @router.patch("/{word_id}", response_model=WordWithProgress)
    def update_word(
        payload: update_schema,  # type: ignore[valid-type]
        word: Word | Phrase = Depends(get_word),
        session: Session = Depends(get_session),
    ) -> Word | Phrase:
        data = payload.model_dump(exclude_unset=True)

        spelling = (data.get("word") or word.word).strip()
        translation = (data.get("translation") or word.translation).strip()
        key = word_key_for(spelling)
        # Правка не должна свести запись к значению, которое уже заведено отдельно
        clash = _same_meaning(session, deck, key, translation, exclude_id=word.id)
        if clash is not None:
            raise _duplicate(clash)

        word.word = spelling
        word.word_key = key
        word.translation = translation
        if "example" in data:
            word.example = (data["example"] or "").strip() or None
        if "example_translation" in data:
            word.example_translation = (data["example_translation"] or "").strip() or None
        if payload.labels is not None:
            word.labels = resolve_labels(session, payload.labels, deck)

        session.flush()
        return word

    @router.put("/{word_id}/status", response_model=WordWithProgress)
    def set_status(
        payload: WordStatusUpdate,
        word: Word | Phrase = Depends(get_word),
        session: Session = Depends(get_session),
    ) -> Word | Phrase:
        """Перевести запись в другой статус вручную — из словаря, а не занятием."""
        set_word_status(session, word, payload.status, utcnow(), deck=deck)
        return word

    @router.put("/{word_id}/priority", response_model=WordWithProgress)
    def set_priority(
        payload: WordPriorityUpdate,
        word: Word | Phrase = Depends(get_word),
        session: Session = Depends(get_session),
    ) -> Word | Phrase:
        """Поднять новую запись в очереди «Изучения» или снять отметку."""
        try:
            set_word_priority(session, word, payload.priority)
        except WordNotNewError:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail="Поднять можно только новое слово"
                if deck is WORDS
                else "Поднять можно только новую фразу",
            ) from None
        return word

    @router.delete("/{word_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_word(
        word: Word | Phrase = Depends(get_word), session: Session = Depends(get_session)
    ) -> Response:
        session.delete(word)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router


router = make_words_router(WORDS, "/words", WordCreate, WordUpdate)
phrases_router = make_words_router(PHRASES, "/phrases", PhraseCreate, PhraseUpdate)
