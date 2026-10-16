"""Импорт слов из CSV-файла: `POST /api/words/import`.

Файл приходит сырым телом `text/csv`, а не формой `multipart/form-data`:
`UploadFile` требует `python-multipart`, новую зависимость ради одного поля.
Декодирует сервер, поэтому ошибку кодировки он видит сам и может её объяснить
(research R1). `default=b""` — потому что без значения по умолчанию пустое тело
дало бы 422 со списком в `detail`, а пустой файл заслуживает своего сообщения.

Роутер отдельный, а не в `make_words_router`: та фабрика общая для слов и
фраз, а импорт есть только у слов (FR-020).
"""

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from app.clock import utcnow
from app.db import get_session
from app.schemas import ImportReport
from app.word_import import ImportFileError, apply_import, parse_import

router = APIRouter(prefix="/words", tags=["words"])


@router.post("/import", response_model=ImportReport)
def import_words(
    content: bytes = Body(default=b"", media_type="text/csv"),
    session: Session = Depends(get_session),
) -> ImportReport:
    try:
        parsed = parse_import(content)
    except ImportFileError as err:
        raise HTTPException(err.status_code, detail=err.detail) from err
    return apply_import(session, parsed, utcnow())
