import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'

import { api } from '../api/client'
import type { ImportReport } from '../api/types'
import { ErrorBox } from './ui'

/**
 * Повторяет `import_max_bytes` из `backend/app/config.py`. Проверка здесь только
 * избавляет от бессмысленной отправки большого файла — решает сервер (research R9).
 */
const IMPORT_MAX_BYTES = 5_000_000

const PRIMARY =
  'rounded-md bg-accent px-4 py-2 font-semibold text-white transition-colors hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-50'
const LINK = 'text-muted underline underline-offset-4 hover:text-ink disabled:opacity-50'

/** Формат файла — до выбора файла (FR-018). */
function FormatHint() {
  return (
    <div className="flex flex-col gap-2 text-sm text-muted">
      <p>
        Первая строка — заголовок. Колонки: <b className="text-ink-soft">слово</b> и{' '}
        <b className="text-ink-soft">перевод</b> (обязательные), пример, перевод примера,
        метка — в любом порядке. Английские названия, как в <code>dictionary.csv</code>{' '}
        (word, translation, example, example_translation, label), тоже подходят.
      </p>
      <p>
        Разделитель «,» или «;» определяется сам. Сохраните файл как «CSV UTF-8».
      </p>
      <p>
        Несколько меток — в одной ячейке через «;». Если «;» разделяет и колонки, возьмите
        ячейку в кавычки: <code>whisk;венчик;;;"Кухня; Посуда"</code>.
      </p>
      <p>
        Существующие слова не дублируются: новый перевод дописывается через «;», пример
        подставляется в пустое поле, метки добавляются. Прогресс не меняется.
      </p>
    </div>
  )
}

function ReportView({ report }: { report: ImportReport }) {
  const unlisted = report.skipped - report.skipped_rows.length
  return (
    <div className="flex flex-col gap-2 text-ink-soft">
      <p>Прочитано строк: {report.rows}</p>
      <p>Добавлено слов: {report.created}</p>
      <p>Дополнено: {report.merged}</p>
      <p>Без изменений: {report.unchanged}</p>
      {report.skipped ? (
        <div>
          <p>Пропущено: {report.skipped}</p>
          <ul className="mt-1 flex flex-col gap-0.5 text-sm">
            {report.skipped_rows.map((row) => (
              <li key={row.line}>
                строка {row.line} — {row.reason}
              </li>
            ))}
            {unlisted > 0 ? <li>и ещё {unlisted}</li> : null}
          </ul>
        </div>
      ) : null}
      {report.labels_created.length ? (
        <div>
          <p>Создано меток: {report.labels_created.length}</p>
          <ul className="mt-1 flex flex-wrap gap-2">
            {report.labels_created.map((name) => (
              <li key={name} className="rounded bg-panel px-2 py-0.5 text-sm">
                {name}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {report.ignored_columns.length ? (
        <p className="text-sm text-muted">
          Колонки не распознаны и пропущены: {report.ignored_columns.join(', ')}
        </p>
      ) : null}
    </div>
  )
}

/**
 * Импорт слов из CSV на «Словаре». Файл разбирает и сливает со словарём
 * сервер; панель отправляет файл и показывает отчёт.
 */
export function ImportPanel({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient()
  const [file, setFile] = useState<File | null>(null)
  const [tooLarge, setTooLarge] = useState(false)

  const mutation = useMutation({
    mutationFn: api.importWords,
    onSuccess: () => {
      // FR-017: список, счётчики меток и новые слова на главной — без перезагрузки
      queryClient.invalidateQueries({ queryKey: ['words'] })
      queryClient.invalidateQueries({ queryKey: ['labels'] })
      queryClient.invalidateQueries({ queryKey: ['overview'] })
    },
  })

  const pick = (picked: File | null) => {
    setFile(picked)
    setTooLarge(false)
    mutation.reset()
  }

  const submit = () => {
    if (!file) return
    if (file.size > IMPORT_MAX_BYTES) {
      setTooLarge(true)
      return
    }
    mutation.mutate(file)
  }

  return (
    <section className="flex flex-col gap-5 rounded-md border border-hairline p-5">
      <div className="flex items-center justify-between gap-4">
        <h2 className="text-lg font-semibold text-ink">Импорт из CSV</h2>
        <button type="button" onClick={onClose} disabled={mutation.isPending} className={LINK}>
          Закрыть
        </button>
      </div>

      {file ? null : <FormatHint />}

      <div className="flex flex-wrap items-center gap-4">
        <input
          type="file"
          accept=".csv,text/csv"
          aria-label="CSV-файл со словами"
          onChange={(event) => pick(event.target.files?.[0] ?? null)}
          disabled={mutation.isPending}
          className="text-ink-soft"
        />
        <button
          type="button"
          onClick={submit}
          disabled={!file || mutation.isPending}
          className={PRIMARY}
        >
          {mutation.isPending ? 'Импортируем…' : 'Импортировать'}
        </button>
      </div>

      {/* 413 и 422 приходят с `detail`, который называет причину */}
      {tooLarge ? <ErrorBox message={`Файл больше ${IMPORT_MAX_BYTES / 1_000_000} МБ`} /> : null}
      {mutation.isError ? <ErrorBox message={mutation.error.message} /> : null}
      {mutation.data ? <ReportView report={mutation.data} /> : null}
    </section>
  )
}
