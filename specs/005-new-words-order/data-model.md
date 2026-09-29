# Data Model: Порядок изучения новых слов и поднятые слова

## Word (таблица `words`) — новое поле

| Поле | Тип | Правила |
|---|---|---|
| `priority` | `BOOLEAN NOT NULL`, `server_default false` | Отметка «Учить первым». `true` только у слова без строки в `progress` |

**Инвариант**: `priority = true` ⇒ у слова нет `progress`.

Держится двумя правилами:

- ставит отметку только `PUT /words/{id}/priority`, и только новому слову (иначе 409);
- любое создание строки `progress` (`select_word`, `set_word_status` со статусом не
  `new`) сбрасывает `priority` в `false` в той же транзакции.

**Жизненный цикл отметки**:

```text
новое, priority=false ──PUT priority:true──▶ новое, priority=true
        ▲                                        │
        └──────────PUT priority:false────────────┘
новое (любое priority) ──«Изучить» / «Уже знаю» / смена статуса──▶ в изучении, priority=false
в изучении ──статус «Новое»──▶ новое, priority=false
```

Импорт (`app/cli.py`) заводит новые строки с `priority=false` по умолчанию колонки
и существующие строки не трогает (FR-015).

**Миграция**: `op.add_column('words', sa.Column('priority', sa.Boolean(),
nullable=False, server_default=sa.false()))`. Таблица не пересоздаётся: пересоздание
`words` через `batch_alter_table` увело бы внешние ключи `progress` и `review_log` на
временную таблицу. `downgrade` удаляет колонку, отметки теряются, прогресс и
расписание не затрагиваются.

## Setting (таблица `settings`) — новый ключ

Таблица есть с начальной миграции, схема не меняется.

| key | value | Умолчание |
|---|---|---|
| `new_words_order` | `oldest_first` \| `newest_first` | строки нет ⇒ `oldest_first` |

Неизвестное значение в базе (правка руками) читается как `oldest_first`, а не
роняет отбор слов.

## NewWordsOrder (перечисление, `schemas.py`)

| Значение | Подпись в интерфейсе | Сортировка новых слов |
|---|---|---|
| `oldest_first` | «В порядке добавления» | `priority DESC, id ASC` |
| `newest_first` | «Сначала недавно добавленные» | `priority DESC, id DESC` |

## Отбор новых слов

`fetch_new_words(session, now, limit, exclude_ids)` сам читает `new_words_order` из
`settings` и передаёт его в `new_words_query`. Отбор:

1. слово без `progress`;
2. не в `exclude_ids`;
3. сортировка из таблицы выше;
4. `LIMIT` = `min(limit, остаток дневного лимита)` — как сейчас.

Этим путём идут все три точки отбора: `GET /study/session?mode=learn`,
замена в `POST /study/select` и `GET /study/new`.
