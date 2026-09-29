"""Импорт словаря: BOM, дубли, идемпотентность."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.cli import import_csv
from app.clock import utcnow
from app.models import Label, Word

# Файл намеренно записывается с BOM — как исходный dictionary.csv
CSV_BODY = '''"word","translation","example","example_translation"
"outsider","посторонний","He is an outsider.","Он посторонний."
"budge","сдвинуть с места","",""
"Outsider","чужак","",""
"outsider","посторонний","",""
"go after","преследовать","",""
"  spaced  ","с пробелами","",""
"","пусто","",""
"noword","","",""
'''


def _write_csv(tmp_path):
    path = tmp_path / "dict.csv"
    path.write_text(CSV_BODY, encoding="utf-8-sig")
    return path


def test_import_deduplicates_and_merges(tmp_path, db_session: Session):
    report = import_csv(_write_csv(tmp_path), db_session)

    assert report.rows == 8
    assert report.skipped == 2  # строка без слова и строка без перевода
    assert report.created == 4  # outsider, budge, go after, spaced

    outsider = db_session.scalar(select(Word).where(Word.word_key == "outsider"))
    # Регистр не создаёт второй записи, а новое значение дописывается к переводу
    assert outsider.translation == "посторонний; чужак"
    # Повторная строка с тем же переводом ничего не добавляет
    assert outsider.translation.count("посторонний") == 1
    assert outsider.example == "He is an outsider."


def test_import_strips_and_normalizes_keys(tmp_path, db_session: Session):
    import_csv(_write_csv(tmp_path), db_session)

    spaced = db_session.scalar(select(Word).where(Word.word_key == "spaced"))
    assert spaced is not None
    assert spaced.word == "spaced"


def test_import_fills_empty_example_on_second_pass(tmp_path, db_session: Session):
    first = tmp_path / "a.csv"
    first.write_text(
        '"word","translation","example","example_translation"\n"brink","край","",""\n',
        encoding="utf-8-sig",
    )
    second = tmp_path / "b.csv"
    second.write_text(
        '"word","translation","example","example_translation"\n'
        '"brink","край","Pushed to the brink.","На край."\n',
        encoding="utf-8-sig",
    )

    import_csv(first, db_session)
    import_csv(second, db_session)

    brink = db_session.scalar(select(Word).where(Word.word_key == "brink"))
    assert brink.example == "Pushed to the brink."
    assert brink.example_translation == "На край."


def test_import_is_idempotent(tmp_path, db_session: Session):
    path = _write_csv(tmp_path)
    import_csv(path, db_session)
    count_after_first = db_session.scalar(select(func.count(Word.id)))

    second = import_csv(path, db_session)

    assert second.created == 0
    assert second.merged == 0
    assert db_session.scalar(select(func.count(Word.id))) == count_after_first


def test_import_keeps_meanings_entered_by_hand(tmp_path, db_session: Session):
    """Слово, заведённое вручную дважды, импорт не сливает и не дублирует."""
    now = utcnow()
    db_session.add_all(
        [
            Word(word="roll out", word_key="roll out", translation="вылезать", created_at=now),
            Word(word="roll out", word_key="roll out", translation="внедрить", created_at=now),
        ]
    )
    db_session.commit()

    path = tmp_path / "roll.csv"
    path.write_text(
        '"word","translation","example","example_translation"\n"roll out","вылезать","",""\n',
        encoding="utf-8-sig",
    )
    report = import_csv(path, db_session)

    assert report.created == 0
    assert report.merged == 0
    # Порядок задаём явно: без ORDER BY SQLite волен вернуть строки в любом
    # порядке, и проверка «значения не слились» превращалась в подбрасывание монеты
    rows = db_session.scalars(
        select(Word).where(Word.word_key == "roll out").order_by(Word.id)
    ).all()
    assert [r.translation for r in rows] == ["вылезать", "внедрить"]


def test_import_keeps_the_priority(tmp_path, db_session: Session):
    path = _write_csv(tmp_path)
    import_csv(path, db_session)
    budge = db_session.scalar(select(Word).where(Word.word_key == "budge"))
    budge.priority = True
    db_session.commit()

    import_csv(path, db_session)

    # FR-015: повторный импорт не трогает отметку «Учить первым»
    db_session.refresh(budge)
    assert budge.priority is True
    others = db_session.scalars(select(Word).where(Word.id != budge.id)).all()
    assert others and not any(w.priority for w in others)


def test_import_keeps_the_labels(tmp_path, db_session: Session):
    path = _write_csv(tmp_path)
    import_csv(path, db_session)
    budge = db_session.scalar(select(Word).where(Word.word_key == "budge"))
    budge.labels.append(Label(name="глаголы", name_key="глаголы"))
    db_session.commit()

    import_csv(path, db_session)

    # FR-016: повторный импорт не трогает разметку и не заводит меток
    db_session.refresh(budge)
    assert [label.name for label in budge.labels] == ["глаголы"]
    assert db_session.scalar(select(func.count(Label.id))) == 1
    others = db_session.scalars(select(Word).where(Word.id != budge.id)).all()
    assert others and not any(w.labels for w in others)
