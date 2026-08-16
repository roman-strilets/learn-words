"""Импорт словаря из CSV.

    uv run --directory backend python -m app.cli import ../dictionary.csv

Импорт идемпотентен: слова дедуплицируются по `word_key`, повторный запуск
не плодит дубли, а лишь дополняет существующие записи.
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select

from app.clock import utcnow
from app.db import SessionLocal
from app.exercises import translation_variants, word_key_for
from app.models import Word

# Файл выгружен с BOM — обычный utf-8 оставил бы «﻿word» в имени первой колонки.
CSV_ENCODING = "utf-8-sig"
REQUIRED_COLUMNS = {"word", "translation"}


@dataclass
class ImportReport:
    rows: int = 0
    created: int = 0
    merged: int = 0
    skipped: int = 0

    def render(self) -> str:
        return (
            f"строк в файле: {self.rows}\n"
            f"добавлено слов: {self.created}\n"
            f"дополнено существующих: {self.merged}\n"
            f"пропущено (пустых): {self.skipped}"
        )


def _merge_translation(existing: str, incoming: str) -> str:
    """Дописать новое значение к переводу, если его там ещё нет."""
    if not incoming:
        return existing
    if translation_variants(incoming) <= translation_variants(existing):
        return existing
    return f"{existing}; {incoming}"


def import_csv(path: Path, session) -> ImportReport:
    report = ImportReport()
    now = utcnow()

    with path.open(encoding=CSV_ENCODING, newline="") as handle:
        reader = csv.DictReader(handle)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise SystemExit(f"В CSV нет обязательных колонок: {', '.join(sorted(missing))}")

        # Существующие слова держим в памяти: 7 тысяч ключей дешевле, чем
        # столько же SELECT-ов по одному.
        index: dict[str, Word] = {w.word_key: w for w in session.scalars(select(Word))}

        for row in reader:
            report.rows += 1
            word_text = (row.get("word") or "").strip()
            translation = (row.get("translation") or "").strip()
            if not word_text or not translation:
                report.skipped += 1
                continue

            key = word_key_for(word_text)
            example = (row.get("example") or "").strip() or None
            example_translation = (row.get("example_translation") or "").strip() or None

            existing = index.get(key)
            if existing is None:
                word = Word(
                    word=word_text,
                    word_key=key,
                    translation=translation,
                    example=example,
                    example_translation=example_translation,
                    created_at=now,
                )
                session.add(word)
                index[key] = word
                report.created += 1
                continue

            changed = False
            merged = _merge_translation(existing.translation, translation)
            if merged != existing.translation:
                existing.translation = merged
                changed = True
            # Пример подставляем только в пустое поле, чтобы не терять исходный.
            if not existing.example and example:
                existing.example = example
                existing.example_translation = example_translation
                changed = True
            if changed:
                report.merged += 1

        session.commit()
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.cli", description="Утилиты словаря")
    sub = parser.add_subparsers(dest="command", required=True)
    importer = sub.add_parser("import", help="Импортировать словарь из CSV")
    importer.add_argument("path", type=Path, help="Путь к CSV-файлу")

    args = parser.parse_args(argv)
    if args.command == "import":
        path: Path = args.path
        if not path.exists():
            print(f"Файл не найден: {path}", file=sys.stderr)
            return 1
        with SessionLocal() as session:
            report = import_csv(path, session)
        print(report.render())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
