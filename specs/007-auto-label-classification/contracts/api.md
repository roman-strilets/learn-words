# API Contract: Автоматическая разметка слов по меткам

Все маршруты под `/api`. Ошибки — `{"detail": "<текст по-русски>"}`: неверное значение
— 422, отсутствие — 404. Новые коды — только у разметки, когда виноват не запрос, а
классификатор: 502 — он ответил ошибкой или недоступен, 504 — не ответил за
`classifier_timeout_seconds` (R6).

## Типы

```text
LabelOut           { id, name, description: str | null, word_count }   # + description
LabelInput         { name: str, description?: str | null }             # POST /labels
LabelUpdate        { name?: str, description?: str | null }            # PATCH /labels/{id}

ClassifyRequest    {
  search?: str, status?: str, priority?: bool, label?: str,   # как query у GET /words
  label_ids: int[],                                           # набор меток, ≥ 1
  from_id?: int,                                              # курсор; нет — с начала
  limit: int                                                  # размер пачки, 1…classifier_batch_max
}
ClassifyResult     { word_id, word, translation, label: LabelRef | null, added: bool }
ClassifyBatch      { results: ClassifyResult[], skipped: int, next_from_id: int | null, remaining: int }

ClassifierSettings { base_url: str, api_key: str, model: str, is_default: bool }
ClassifierInput    { base_url: str, api_key: str, model: str }
ClassifierCheck    { ok: bool, detail: str }
```

`description`: обрезается; пустая строка → `null`; длиннее 200 — 422.

## Метки (изменения)

### `GET /labels` → 200 `LabelOut[]`

Без изменений, кроме поля `description`.

### `POST /labels` ← `LabelInput` → 201 `LabelOut`

Принимает необязательное `description`. Остальное как раньше.

### `PATCH /labels/{id}` ← `LabelUpdate` → 200 `LabelOut`

Частичное обновление: меняются только переданные поля. `{ "name": "…" }` — прежнее
переименование, описание не трогается. `{ "description": null }` или `""` — описание
стирается.
- 422 — не передано ни одного поля; название или описание не проходят проверку.
- 409, 404 — как раньше.

## Слова (изменение)

### `GET /words?…&from_id=<int>` → 200 `WordPage`

Новый необязательный параметр `from_id` (≥ 1): только записи с `id ≥ from_id`.
Складывается с остальными фильтрами. Нужен панели разметки, чтобы до запуска показать,
сколько слов попадёт в этап (`total` при `limit=1`), и найти слово «Начать с».

## Разметка

### `POST /labels/classify` ← `ClassifyRequest` → 200 `ClassifyBatch`

Одна пачка. Сервер:

1. выбирает до `limit` записей, подходящих под фильтры, с `id ≥ from_id`, по
   возрастанию `id` — тот же отбор, что у `GET /words` (общая функция, R3);
2. закрывает транзакцию чтения и спрашивает классификатор (R5);
3. в новой транзакции ставит каждому слову выбранную метку, если её на нём нет, и
   коммитит пачку целиком (FR-011, FR-016).

Ответ:
- `results` — по записи на каждое обработанное слово в порядке `id`. `label` —
  выбранная метка или `null` («ни одна не подходит», ответ вне набора). `added` —
  `true`, только если метка поставлена этим запросом; уже стоявшая — `false`.
- `skipped` — сколько выбранных слов удалили, пока шёл запрос: они не обработаны.
- `next_from_id` — курсор следующей пачки (`id` последнего слова + 1); `null`, если
  после этой пачки подходящих слов нет.
- `remaining` — сколько подходящих слов осталось с `id ≥ next_from_id`.

Правила:
- Метки из `label_ids`, которых уже нет, молча пропускаются (метку удалили во
  время разметки). Если не осталось ни одной — 422 «Нет меток для разметки».
- Пустая выборка — 200 с `results: []`, `next_from_id: null`, `remaining: 0`;
  классификатор не вызывается.
- Метки не снимаются; `progress`, `review_log`, `words` не меняются.
- 422 — `label_ids` пуст, `limit` вне 1…`classifier_batch_max`, неизвестный `status`
  или `label` (тексты те же, что у `GET /words`).
- 502 — классификатор недоступен, отклонил ключ, не знает модель или ответил не по
  схеме; `detail` называет причину. Ни одна метка пачки не поставлена.
- 504 — нет ответа за `classifier_timeout_seconds`. Ни одна метка пачки не поставлена.

## Настройки классификатора

### `GET /settings/classifier` → 200 `ClassifierSettings`

Действующие значения. `is_default` — `true`, если ни одно не сохранено и действуют
значения из `config.py`.

### `PUT /settings/classifier` ← `ClassifierInput` → 200 `ClassifierSettings`

Сохраняет все три значения разом. Подключение не проверяет.
- 422 — адрес не `http(s)://…`, поле пустое или длиннее предела (data-model).

### `DELETE /settings/classifier` → 200 `ClassifierSettings`

Удаляет сохранённые значения и возвращает значения по умолчанию (`is_default: true`).

### `POST /settings/classifier/check` ← `ClassifierInput` → 200 `ClassifierCheck`

Проверяет переданные — не обязательно сохранённые — значения одним коротким вопросом
модели (R7) с таймаутом `classifier_check_timeout_seconds`. Неудача — не ошибка
запроса, а ответ: `{ "ok": false, "detail": "Модель «nimbel» не найдена" }`.
- 422 — значения не проходят проверку, как у `PUT`.
