"""Разбор CSV для импорта из интерфейса: без базы, таблицами."""

import pytest

from app.config import settings
from app.word_import import (
    ImportFileError,
    ImportRow,
    SkippedRow,
    detect_delimiter,
    parse_import,
)

BOM = "﻿"


def _parse(text: str, encoding: str = "utf-8"):
    return parse_import(text.encode(encoding))


def _row(line: int, word: str, translation: str, **extra) -> ImportRow:
    return ImportRow(
        line=line,
        word=word,
        translation=translation,
        example=extra.get("example"),
        example_translation=extra.get("example_translation"),
        labels=extra.get("labels", []),
    )


# ----------------------------------------------------------------- разделитель


@pytest.mark.parametrize(
    "text",
    [
        "слово;перевод\nsaucepan;кастрюля, сотейник\n",
        '"слово","перевод"\nsaucepan,"кастрюля, сотейник"\n',
        # В заголовке «;» больше: запятые в данных голос не имеют
        "слово;перевод;пример\nsaucepan;кастрюля, сотейник;\n",
    ],
)
def test_delimiter_is_taken_from_the_header(text: str):
    parsed = _parse(text)

    assert parsed.rows == [_row(2, "saucepan", "кастрюля, сотейник")]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("слово;перевод", ";"),
        ("слово,перевод", ","),
        # Одна колонка и равенство — запятая
        ("слово", ","),
        ("a;b,c", ","),
        ("a;b;c,d", ";"),
        # Разделитель в кавычках не считается
        ('"a;b;c",d', ","),
        ('"a,b,c";d', ";"),
        # Считается только заголовок: запятые в переводах не голосуют
        ('слово;перевод\n"x",кастрюля, сотейник, ковш', ";"),
        # Перевод строки в кавычках заголовок не обрывает
        ('"сло\nво";перевод\na,b,c,d', ";"),
    ],
)
def test_detect_delimiter(text: str, expected: str):
    assert detect_delimiter(text) == expected


def test_single_column_header_reads_with_a_comma():
    with pytest.raises(ImportFileError) as error:
        _parse("слово\nsaucepan\n")

    assert error.value.status_code == 422
    assert "Нет обязательных колонок: перевод." in error.value.detail


# -------------------------------------------------------------------- кодировка


@pytest.mark.parametrize("prefix", ["", BOM])
def test_bom_is_optional_and_never_leaks(prefix: str):
    parsed = _parse(f"{prefix}word,translation\nbrink,край\n")

    assert parsed.rows == [_row(2, "brink", "край")]
    assert parsed.ignored_columns == []


# ---------------------------------------------------------------------- колонки


@pytest.mark.parametrize(
    "header",
    [
        "слово;перевод;пример;перевод примера;метка",
        "word;translation;example;example_translation;label",
        "Слово;ПЕРЕВОД;Пример использования;Перевод примера;Метки",
        "  word ;Translation;EXAMPLE; example translation ;Labels",
        "слово;перевод;пример;перевод примёра;метка",
    ],
)
def test_russian_and_english_headers_mean_the_same(header: str):
    parsed = _parse(f"{header}\nsaucepan;кастрюля;On the stove.;На плите.;Кухня\n")

    assert parsed.rows == [
        _row(
            2,
            "saucepan",
            "кастрюля",
            example="On the stove.",
            example_translation="На плите.",
            labels=["Кухня"],
        )
    ]


def test_columns_are_matched_by_name_in_any_order():
    parsed = _parse(
        "метка;перевод примера;пример;перевод;слово\nКухня;На плите.;On it.;кастрюля;pan\n"
    )

    assert parsed.rows == [
        _row(
            2,
            "pan",
            "кастрюля",
            example="On it.",
            example_translation="На плите.",
            labels=["Кухня"],
        )
    ]


def test_dictionary_csv_header_is_accepted():
    text = (
        f'{BOM}"word","translation","example","example_translation"\n'
        '"outsider","посторонний","He is an outsider.","Он посторонний."\n'
    )

    parsed = _parse(text)

    assert parsed.rows == [
        _row(
            2,
            "outsider",
            "посторонний",
            example="He is an outsider.",
            example_translation="Он посторонний.",
        )
    ]
    assert parsed.ignored_columns == []


@pytest.mark.parametrize(
    ("header", "missing"),
    [
        ("слово;пример", "перевод"),
        ("перевод;метка", "слово"),
        ("пример;метка", "слово, перевод"),
    ],
)
def test_missing_required_columns_reject_the_file(header: str, missing: str):
    with pytest.raises(ImportFileError) as error:
        _parse(f"{header}\nx;y\n")

    assert error.value.status_code == 422
    assert error.value.detail == (
        f"Нет обязательных колонок: {missing}. "
        "Ожидаются: слово, перевод, пример, перевод примера, метка"
    )


# ----------------------------------------------------------------------- ячейки


def test_quoted_cell_keeps_the_delimiter_and_a_newline():
    parsed = _parse(
        'слово;перевод;пример\nroll out;"внедрить; раскатать";"Line one\nline two"\n'
    )

    assert parsed.rows == [
        _row(2, "roll out", "внедрить; раскатать", example="Line one\nline two")
    ]


@pytest.mark.parametrize(
    ("cell", "labels"),
    [
        ('"Кухня; посуда;;"', ["Кухня", "посуда"]),
        ("Кухня", ["Кухня"]),
        ('"  ; "', []),
        ("", []),
    ],
)
def test_label_cell_is_split_on_semicolons(cell: str, labels: list[str]):
    parsed = _parse(f"слово;перевод;метка\npan;кастрюля;{cell}\n")

    assert parsed.rows[0].labels == labels


@pytest.mark.parametrize(
    ("example", "example_translation", "expected"),
    [
        ("", "На плите.", (None, None)),
        ("  ", "", (None, None)),
        ("On it.", "", ("On it.", None)),
        (" On it. ", " На плите. ", ("On it.", "На плите.")),
    ],
)
def test_example_translation_needs_an_example(
    example: str, example_translation: str, expected: tuple
):
    parsed = _parse(
        f"слово;перевод;пример;перевод примера\npan;кастрюля;{example};{example_translation}\n"
    )

    row = parsed.rows[0]
    assert (row.example, row.example_translation) == expected


def test_values_are_stripped():
    parsed = _parse("слово;перевод\n  spaced  ;  с пробелами  \n")

    assert parsed.rows == [_row(2, "spaced", "с пробелами")]


# ------------------------------------------------------------- номера и пропуски


def test_line_numbers_follow_the_spreadsheet():
    text = (
        "слово;перевод;пример\n"
        'a;а;"two\nlines"\n'
        "\n"
        ";;\n"
        "b;б;\n"
    )

    parsed = _parse(text)

    # Запись с переводом строки в кавычках — одна строка таблицы,
    # пустые строки — тоже строки таблицы, но не данные
    assert [row.line for row in parsed.rows] == [2, 5]
    assert parsed.total_rows == 2
    assert parsed.skipped == []


@pytest.mark.parametrize(
    ("line", "reason"),
    [
        (";кастрюля", "нет слова"),
        ("pan;", "нет перевода"),
        ("  ;  ", None),
        (";", None),
    ],
)
def test_rows_without_a_word_or_a_translation_are_skipped(line: str, reason: str | None):
    parsed = _parse(f"слово;перевод\nok;хорошо\n{line}\n")

    assert parsed.rows == [_row(2, "ok", "хорошо")]
    if reason is None:
        assert parsed.skipped == []
        assert parsed.total_rows == 1
    else:
        assert parsed.skipped == [SkippedRow(line=3, reason=reason)]
        assert parsed.total_rows == 2


def test_short_rows_read_missing_cells_as_empty():
    parsed = _parse("слово;перевод;пример;метка\npan;кастрюля\n")

    assert parsed.rows == [_row(2, "pan", "кастрюля")]


# ----------------------------------------------------------- длины и чужие колонки

LONG_WORD = "w" * 129
LONG_LABEL = "м" * 51


@pytest.mark.parametrize(
    ("line", "reason"),
    [
        (f"{LONG_WORD};перевод;", "слово длиннее 128 символов"),
        (f"pan;кастрюля;{LONG_LABEL}", f"метка «{LONG_LABEL}» длиннее 50 символов"),
        # Плохая метка пропускает всю строку, а не одну метку
        (f'pan;кастрюля;"Кухня; {LONG_LABEL}"', f"метка «{LONG_LABEL}» длиннее 50 символов"),
    ],
)
def test_too_long_values_skip_the_row(line: str, reason: str):
    parsed = _parse(f"слово;перевод;метка\nok;хорошо;\n{line}\n")

    assert parsed.rows == [_row(2, "ok", "хорошо")]
    assert parsed.skipped == [SkippedRow(line=3, reason=reason)]
    assert parsed.total_rows == 2


def test_limits_match_the_form():
    parsed = _parse(f"слово;перевод;метка\n{'w' * 128};перевод;{'м' * 50}\n")

    assert parsed.skipped == []
    assert parsed.rows[0].labels == ["м" * 50]


def test_unknown_columns_are_listed_as_ignored():
    parsed = _parse("Источник;слово;перевод;;Заметки\nкнига;pan;кастрюля;;\n")

    assert parsed.ignored_columns == ["Источник", "Заметки"]
    assert parsed.rows == [_row(2, "pan", "кастрюля")]


@pytest.mark.parametrize(
    ("header", "column"),
    [
        ("слово;перевод;translation", "перевод"),
        ("word;слово;перевод", "слово"),
        ("слово;перевод;метка;labels", "метка"),
        ("слово;перевод;пример;пример использования", "пример"),
    ],
)
def test_a_field_named_twice_rejects_the_file(header: str, column: str):
    with pytest.raises(ImportFileError) as error:
        _parse(f"{header}\n")

    assert error.value.status_code == 422
    assert error.value.detail == f"Колонка «{column}» встречается дважды"


@pytest.mark.parametrize("content", [b"", b"   \n\n  ", BOM.encode(), b"\xef\xbb\xbf\r\n"])
def test_empty_file_is_rejected(content: bytes):
    with pytest.raises(ImportFileError) as error:
        parse_import(content)

    assert error.value.status_code == 422
    assert error.value.detail == "Файл пустой"


def test_windows_1251_is_rejected_with_a_hint():
    with pytest.raises(ImportFileError) as error:
        _parse("слово;перевод\nкастрюля;pan\n", encoding="cp1251")

    assert error.value.status_code == 422
    assert error.value.detail == "Файл не в UTF-8 — сохраните его как «CSV UTF-8»"


def test_header_only_file_has_no_rows():
    parsed = _parse("слово;перевод\n")

    assert parsed.rows == []
    assert parsed.skipped == []
    assert parsed.total_rows == 0


def test_too_large_file_is_rejected_before_decoding(monkeypatch):
    monkeypatch.setattr(settings, "import_max_bytes", 5_000_000)
    content = b"\xff" * (settings.import_max_bytes + 1)

    with pytest.raises(ImportFileError) as error:
        parse_import(content)

    assert error.value.status_code == 413
    assert error.value.detail == "Файл больше 5 МБ"
