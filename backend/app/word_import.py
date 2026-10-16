"""Импорт слов из CSV-файла, присланного из интерфейса.

Модуль делится на две части (research R5, R6):

- `parse_import` — чистый разбор файла без базы: кодировка, разделитель,
  колонки и проверка строк. Его проверяют табличные тесты;
- `apply_import` — применение разобранных строк к словарю в одной транзакции.

Здесь же живут правила слияния, общие с консольным импортом (`app/cli.py`):
оба способа должны давать одинаковый словарь.
"""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.exercises import translation_variants, word_key_for
from app.labels_service import label_key, label_sort_key, resolve_labels
from app.models import Label, Word
from app.schemas import LABEL_NAME_MAX, WORD_MAX_LENGTH, ImportReport, ImportSkippedRow

# Поля импорта. Названия — те, что показываются пользователю в сообщениях
WORD = "слово"
TRANSLATION = "перевод"
EXAMPLE = "пример"
EXAMPLE_TRANSLATION = "перевод примера"
LABELS = "метка"

FIELDS = (WORD, TRANSLATION, EXAMPLE, EXAMPLE_TRANSLATION, LABELS)
REQUIRED_FIELDS = (WORD, TRANSLATION)

# Названия колонок после `_normalize_header` → поле. Русские — как их назвал
# пользователь, английские — как в поставляемом `dictionary.csv` (research R4)
COLUMN_ALIASES: dict[str, str] = {
    "слово": WORD,
    "word": WORD,
    "перевод": TRANSLATION,
    "translation": TRANSLATION,
    "пример": EXAMPLE,
    "пример использования": EXAMPLE,
    "example": EXAMPLE,
    "перевод примера": EXAMPLE_TRANSLATION,
    "example translation": EXAMPLE_TRANSLATION,
    "метка": LABELS,
    "метки": LABELS,
    "label": LABELS,
    "labels": LABELS,
}

# Несколько меток в одной ячейке
LABEL_SEPARATOR = ";"
CANDIDATE_DELIMITERS = (",", ";")
# Номер первой записи в табличном редакторе: строка 1 — заголовок
FIRST_DATA_LINE = 2
BYTES_IN_MB = 1_000_000


class ImportFileError(ValueError):
    """Файл нельзя импортировать целиком: импорт не начинается, словарь не меняется.

    `status_code` — ответ роутера: 413 для слишком большого файла, 422 для
    остального.
    """

    def __init__(self, detail: str, status_code: int = 422) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def row_for_translation(rows: list[Word], translation: str) -> Word | None:
    """Куда дописывать значение из CSV.

    У слова может быть несколько записей — по одной на значение, заведённых
    вручную. Импорт дописывает в ту, где это значение уже есть, а если такой
    нет — в первую: новые записи под каждое значение он не плодит.
    """
    if not rows:
        return None
    variants = translation_variants(translation)
    for row in rows:
        if translation_variants(row.translation) & variants:
            return row
    return rows[0]


def merge_translation(existing: str, incoming: str) -> str:
    """Дописать новое значение к переводу, если его там ещё нет."""
    if not incoming:
        return existing
    if translation_variants(incoming) <= translation_variants(existing):
        return existing
    return f"{existing}; {incoming}"


# ------------------------------------------------------------------------ разбор


@dataclass(frozen=True)
class ImportRow:
    """Строка файла, принятая к импорту. `line` — номер строки в табличном редакторе."""

    line: int
    word: str
    translation: str
    example: str | None
    example_translation: str | None
    labels: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SkippedRow:
    """Строка файла, пропущенная с причиной."""

    line: int
    reason: str


@dataclass(frozen=True)
class ParsedImport:
    """Разобранный файл: принятые строки в порядке файла, пропуски и чужие колонки.

    `total_rows` — непустые строки данных, то есть `rows` плюс `skipped`.
    """

    rows: list[ImportRow]
    skipped: list[SkippedRow]
    ignored_columns: list[str]
    total_rows: int


def detect_delimiter(text: str) -> str:
    """Разделитель колонок по строке заголовка: «;» или «,», которого больше вне кавычек.

    Решает заголовок, а не данные: переводы вида «кастрюля, сотейник» полны
    запятых, и `csv.Sniffer` по ним гадает неверно. В названиях колонок
    разделителей не бывает, поэтому подсчёт по заголовку детерминирован. При
    равенстве (в том числе в файле из одной колонки) — запятая (research R3).
    """
    counts = dict.fromkeys(CANDIDATE_DELIMITERS, 0)
    quoted = False
    for char in text:
        if char == '"':
            # Удвоенная кавычка внутри значения дважды переключает состояние
            quoted = not quoted
        elif quoted:
            continue
        elif char in "\r\n":
            break
        elif char in counts:
            counts[char] += 1
    return ";" if counts[";"] > counts[","] else ","


def _normalize_header(name: str) -> str:
    """Название колонки без регистра, крайних пробелов, «_» и «ё»."""
    name = name.casefold().replace("_", " ").replace("ё", "е")
    return " ".join(name.split())


def _map_columns(header: list[str]) -> tuple[dict[str, int], list[str]]:
    """Поле → номер колонки и исходные названия нераспознанных колонок.

    Колонки узнаются по названию, а не по позиции: лишняя колонка в начале
    сдвинула бы все значения, и словарь молча наполнился бы примерами вместо
    переводов (research R4).
    """
    columns: dict[str, int] = {}
    ignored: list[str] = []
    for index, name in enumerate(header):
        normalized = _normalize_header(name)
        field_name = COLUMN_ALIASES.get(normalized)
        if field_name is None:
            if normalized:
                ignored.append(name.strip())
            continue
        if field_name in columns:
            # Какую из двух колонок брать — не угадать, а ошибиться значит
            # молча наполнить словарь не теми значениями
            raise ImportFileError(f"Колонка «{field_name}» встречается дважды")
        columns[field_name] = index

    missing = [name for name in REQUIRED_FIELDS if name not in columns]
    if missing:
        raise ImportFileError(
            f"Нет обязательных колонок: {', '.join(missing)}. "
            f"Ожидаются: {', '.join(FIELDS)}"
        )
    return columns, ignored


def _split_labels(cell: str) -> list[str]:
    return [name for name in (part.strip() for part in cell.split(LABEL_SEPARATOR)) if name]


def _row_problem(word: str, translation: str, labels: list[str]) -> str | None:
    """Причина пропустить строку или `None`, если строка годится.

    Пределы — те же, что у ручной формы. Строка с плохой меткой пропускается
    целиком: слово без неё пришлось бы потом размечать руками (research R7).
    """
    if not word:
        return "нет слова"
    if not translation:
        return "нет перевода"
    if len(word) > WORD_MAX_LENGTH:
        return f"слово длиннее {WORD_MAX_LENGTH} символов"
    for name in labels:
        if len(name) > LABEL_NAME_MAX:
            return f"метка «{name}» длиннее {LABEL_NAME_MAX} символов"
    return None


def parse_import(content: bytes) -> ParsedImport:
    """Разобрать CSV-файл без обращения к базе.

    Ошибка уровня файла — `ImportFileError`: тогда импорт не начинается.
    Плохая строка файл не отклоняет, а становится `SkippedRow` с причиной.
    """
    if len(content) > settings.import_max_bytes:
        limit = settings.import_max_bytes / BYTES_IN_MB
        raise ImportFileError(f"Файл больше {limit:g} МБ", status_code=413)
    try:
        # `utf-8-sig` снимает BOM: иначе он прилип бы к названию первой колонки
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as err:
        # Кодировку не угадываем: cp1251 «успешно» прочитает и мусор, а
        # испорченный словарь хуже отказа с понятной причиной (research R2)
        raise ImportFileError("Файл не в UTF-8 — сохраните его как «CSV UTF-8»") from err
    if not text.strip():
        raise ImportFileError("Файл пустой")
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=detect_delimiter(text))
    header = next(reader, [])
    columns, ignored = _map_columns(header)

    def cell(record: list[str], name: str) -> str:
        index = columns.get(name)
        if index is None or index >= len(record):
            return ""
        return record[index].strip()

    rows: list[ImportRow] = []
    skipped: list[SkippedRow] = []
    # Номер — по записи, а не по физической строке: ячейка с переводом строки
    # в кавычках в табличном редакторе остаётся одной строкой
    for offset, record in enumerate(reader):
        line = offset + FIRST_DATA_LINE
        if not any(value.strip() for value in record):
            continue
        word = cell(record, WORD)
        translation = cell(record, TRANSLATION)
        labels = _split_labels(cell(record, LABELS))
        problem = _row_problem(word, translation, labels)
        if problem is not None:
            skipped.append(SkippedRow(line=line, reason=problem))
            continue
        # Перевод примера без самого примера показать негде
        example = cell(record, EXAMPLE) or None
        example_translation = (cell(record, EXAMPLE_TRANSLATION) or None) if example else None
        rows.append(
            ImportRow(
                line=line,
                word=word,
                translation=translation,
                example=example,
                example_translation=example_translation,
                labels=labels,
            )
        )

    return ParsedImport(
        rows=rows,
        skipped=skipped,
        ignored_columns=ignored,
        total_rows=len(rows) + len(skipped),
    )


# -------------------------------------------------------------------- применение


def apply_import(session: Session, parsed: ParsedImport, now: datetime) -> ImportReport:
    """Применить разобранные строки к словарю слов.

    Новое слово заводится без прогресса — со статусом «Новое», как после ручного
    добавления. Прогресс, `priority` и журналы ответов не трогаются: импорт —
    правка словаря, а не ответ на упражнение (конституция I, IV). Весь файл
    идёт в транзакции вызывающего, поэтому любое исключение оставляет словарь
    таким, каким он был (FR-015).
    """
    # Словарь держим в памяти: тысячи строк файла не превращаются в тысячи
    # SELECT-ов, а метки грузятся сразу, без запроса на каждое слово (research R8)
    index: dict[str, list[Word]] = defaultdict(list)
    for word in session.scalars(
        select(Word).options(selectinload(Word.labels)).order_by(Word.id)
    ):
        index[word.word_key].append(word)

    # Новые метки определяются сравнением с тем, что было до прохода, а не по
    # `id is None`: тот зависит от того, успела ли сессия сбросить их в базу
    labels: dict[str, Label] = {
        label.name_key: label for label in session.scalars(select(Label))
    }
    new_names: dict[str, str] = {}
    for row in parsed.rows:
        for name in row.labels:
            key = label_key(name)
            if key not in labels:
                new_names.setdefault(key, name)
    created_labels = resolve_labels(session, list(new_names.values())) if new_names else []
    for label in created_labels:
        labels[label.name_key] = label

    created = merged = unchanged = 0
    for row in parsed.rows:
        row_labels = _row_labels(row, labels)
        key = word_key_for(row.word)
        if not index[key]:
            word = Word(
                word=row.word,
                word_key=key,
                translation=row.translation,
                example=row.example,
                example_translation=row.example_translation,
                created_at=now,
                labels=row_labels,
            )
            session.add(word)
            index[key].append(word)
            created += 1
            continue

        # Правила слияния — те же, что у консольного импорта, намеренно: оба
        # способа должны давать одинаковый словарь (Clarifications спецификации).
        # Перевод, пример и метки записи только дополняются, не заменяются
        target = row_for_translation(index[key], row.translation)
        assert target is not None  # у слова есть записи — значит, есть куда писать
        if _merge_row(target, row, row_labels):
            merged += 1
        else:
            unchanged += 1

    # Вставки идут в порядке `session.add`, поэтому `id` новых слов растут в
    # порядке строк файла, и «В порядке добавления» учит их так же (FR-019)
    session.flush()
    return ImportReport(
        rows=parsed.total_rows,
        created=created,
        merged=merged,
        unchanged=unchanged,
        skipped=len(parsed.skipped),
        # Поимённо — только первые пропуски, полное число — в `skipped`
        skipped_rows=[
            ImportSkippedRow(line=item.line, reason=item.reason)
            for item in parsed.skipped[: settings.import_skipped_report_max]
        ],
        labels_created=[label.name for label in created_labels],
        ignored_columns=parsed.ignored_columns,
    )


def _merge_row(target: Word, row: ImportRow, row_labels: list[Label]) -> bool:
    """Дописать строку в существующую запись; `True`, если запись изменилась.

    Прогресс и `priority` записи не трогаются.
    """
    changed = False
    translation = merge_translation(target.translation, row.translation)
    if translation != target.translation:
        target.translation = translation
        changed = True
    # Пример подставляем только в пустое поле, чтобы не терять исходный
    if not target.example and row.example:
        target.example = row.example
        target.example_translation = row.example_translation
        changed = True
    present = {label.name_key for label in target.labels}
    for label in row_labels:
        if label.name_key not in present:
            target.labels.append(label)
            present.add(label.name_key)
            changed = True
    return changed


def _row_labels(row: ImportRow, labels: dict[str, Label]) -> list[Label]:
    """Метки строки без повторов, в порядке меток словаря."""
    unique = {label_key(name): labels[label_key(name)] for name in row.labels}
    return sorted(unique.values(), key=lambda label: label_sort_key(label.name_key))
