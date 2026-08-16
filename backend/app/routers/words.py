from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.clock import utcnow
from app.db import get_session
from app.exercises import word_key_for
from app.models import Progress, Word, WordStatus
from app.routers.deps import get_word
from app.schemas import WordCreate, WordOut, WordPage, WordUpdate, WordWithProgress

router = APIRouter(prefix="/words", tags=["words"])


@router.get("", response_model=WordPage)
def list_words(
    search: str | None = Query(default=None, description="Подстрока в слове или переводе"),
    status_filter: str | None = Query(
        default=None,
        alias="status",
        description="new | learning | review | known | suspended",
    ),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> WordPage:
    stmt = select(Word).outerjoin(Progress, Progress.word_id == Word.id)

    if search:
        pattern = f"%{search.strip().lower()}%"
        stmt = stmt.where(
            or_(func.lower(Word.word).like(pattern), func.lower(Word.translation).like(pattern))
        )

    if status_filter == "new":
        stmt = stmt.where(Progress.word_id.is_(None))
    elif status_filter:
        if status_filter not in {s.value for s in WordStatus}:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Неизвестный статус")
        stmt = stmt.where(Progress.status == status_filter)

    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = session.scalars(stmt.order_by(Word.id).limit(limit).offset(offset)).all()

    return WordPage(
        items=[WordWithProgress.model_validate(w) for w in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=WordOut, status_code=status.HTTP_201_CREATED)
def create_word(payload: WordCreate, session: Session = Depends(get_session)) -> Word:
    key = word_key_for(payload.word)
    existing = session.scalar(select(Word).where(Word.word_key == key))
    if existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"Слово «{existing.word}» уже есть в словаре (перевод: {existing.translation})",
        )

    word = Word(
        word=payload.word,
        word_key=key,
        translation=payload.translation,
        example=payload.example,
        example_translation=payload.example_translation,
        created_at=utcnow(),
    )
    session.add(word)
    session.flush()
    return word


@router.get("/{word_id}", response_model=WordWithProgress)
def get_word_detail(word: Word = Depends(get_word)) -> Word:
    return word


@router.patch("/{word_id}", response_model=WordWithProgress)
def update_word(
    payload: WordUpdate,
    word: Word = Depends(get_word),
    session: Session = Depends(get_session),
) -> Word:
    data = payload.model_dump(exclude_unset=True)

    if "word" in data and data["word"]:
        key = word_key_for(data["word"])
        clash = session.scalar(select(Word).where(Word.word_key == key, Word.id != word.id))
        if clash is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Такое слово уже есть в словаре")
        word.word = data["word"].strip()
        word.word_key = key

    if data.get("translation"):
        word.translation = data["translation"].strip()
    if "example" in data:
        word.example = (data["example"] or "").strip() or None
    if "example_translation" in data:
        word.example_translation = (data["example_translation"] or "").strip() or None

    session.flush()
    return word


@router.delete("/{word_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_word(
    word: Word = Depends(get_word), session: Session = Depends(get_session)
) -> Response:
    session.delete(word)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
