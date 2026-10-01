import { useState } from 'react'
import type { FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '../api/client'
import type { ClassifierInput, ClassifierSettings } from '../api/types'
import { ErrorBox, Spinner, TextField } from './ui'

const PRIMARY =
  'rounded-md bg-accent px-4 py-2 font-semibold text-white transition-colors hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-50'
const SECONDARY =
  'rounded-md bg-panel px-4 py-2 text-ink-soft transition-colors hover:bg-hairline disabled:cursor-not-allowed disabled:opacity-50'

/** Форма подключения: поля живут локально, чтобы проверять несохранённое. */
function ClassifierForm({ initial }: { initial: ClassifierSettings }) {
  const queryClient = useQueryClient()
  const [values, setValues] = useState<ClassifierInput>({
    base_url: initial.base_url,
    api_key: initial.api_key,
    model: initial.model,
  })
  const [isDefault, setIsDefault] = useState(initial.is_default)

  const apply = (saved: ClassifierSettings) => {
    queryClient.setQueryData(['classifier'], saved)
    setValues({ base_url: saved.base_url, api_key: saved.api_key, model: saved.model })
    setIsDefault(saved.is_default)
  }

  // На 422 введённое остаётся в полях — его можно поправить
  const save = useMutation({ mutationFn: api.saveClassifier, onSuccess: apply })
  const reset = useMutation({ mutationFn: api.resetClassifier, onSuccess: apply })
  const check = useMutation({ mutationFn: api.checkClassifier })

  const set = (field: keyof ClassifierInput) => (value: string) => {
    setValues((prev) => ({ ...prev, [field]: value }))
    save.reset()
    check.reset()
  }

  const submit = (event: FormEvent) => {
    event.preventDefault()
    save.mutate(values)
  }

  const busy = save.isPending || reset.isPending
  const failure = save.error ?? reset.error ?? check.error

  return (
    <form onSubmit={submit} className="flex flex-col gap-4">
      <TextField label="Адрес сервиса" value={values.base_url} onChange={set('base_url')} />
      <TextField label="Ключ доступа" value={values.api_key} onChange={set('api_key')} />
      <TextField label="Модель" value={values.model} onChange={set('model')} />

      <p className="text-sm text-muted">
        {isDefault
          ? 'Действуют значения по умолчанию.'
          : 'Действуют сохранённые значения.'}{' '}
        Ключ хранится в базе приложения открытым текстом — не вводите сюда ключ, который
        жалко потерять.
      </p>

      <div className="flex flex-wrap items-center gap-3">
        <button type="submit" disabled={busy} className={PRIMARY}>
          {save.isPending ? 'Сохраняем…' : 'Сохранить'}
        </button>
        <button
          type="button"
          onClick={() => check.mutate(values)}
          disabled={check.isPending}
          className={SECONDARY}
        >
          {check.isPending ? 'Проверяем…' : 'Проверить подключение'}
        </button>
        <button
          type="button"
          onClick={() => {
            check.reset()
            reset.mutate()
          }}
          disabled={busy}
          className="text-muted underline underline-offset-4 hover:text-ink disabled:opacity-50"
        >
          Сбросить
        </button>
        {save.isSuccess ? <span className="text-sm text-correct">Сохранено</span> : null}
      </div>

      {failure ? <ErrorBox message={failure.message} /> : null}
      {check.data ? (
        check.data.ok ? (
          <p className="text-correct">{check.data.detail}</p>
        ) : (
          <ErrorBox message={check.data.detail} />
        )
      ) : null}
    </form>
  )
}

/**
 * Вкладка «Разметка»: куда автоматическая разметка ходит за моделью.
 * Значения хранятся на сервере и действуют в любом браузере.
 */
export function ClassifierSection() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['classifier'],
    queryFn: api.getClassifier,
  })

  return (
    <section className="flex flex-col gap-6">
      <h2 className="text-lg font-semibold text-ink-soft">Подключение к модели</h2>
      <p className="text-muted">
        Автоматическая разметка на «Словаре» спрашивает языковую модель, какую метку
        поставить слову. По умолчанию это локальная Ollama с моделью nimble.
        «Проверить подключение» задаёт модели один короткий вопрос с введёнными
        значениями, не сохраняя их.
      </p>

      {error ? <ErrorBox message={error.message} /> : null}
      {isLoading ? <Spinner /> : null}
      {data ? <ClassifierForm initial={data} /> : null}
    </section>
  )
}
