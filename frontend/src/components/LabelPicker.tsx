import { useId, useState } from 'react'
import type { KeyboardEvent } from 'react'
import { useQuery } from '@tanstack/react-query'

import { api } from '../api/client'

/** Совпадает с `LABEL_NAME_MAX` на сервере: длиннее он ответит 422. */
const LABEL_NAME_MAX = 50

type Option = { kind: 'existing'; name: string } | { kind: 'create'; name: string }

const same = (a: string, b: string) => a.toLocaleLowerCase() === b.toLocaleLowerCase()

/**
 * Поле меток в форме слова: выбранные метки — чипами, под полем по мере ввода
 * подсказываются существующие и пункт «Создать метку «…»».
 *
 * Своё, а не `<datalist>`: тот не умеет ни чипов, ни пункта «Создать». Метки
 * уходят на сервер названиями вместе со словом, поэтому новая метка появляется
 * только при сохранении: отменённая правка ничего не создаёт.
 *
 * Ошибку загрузки списка не показываем: без подсказок метку всё равно можно
 * создать.
 */
export function LabelPicker({
  value,
  onChange,
}: {
  value: string[]
  onChange: (next: string[]) => void
}) {
  const id = useId()
  const [text, setText] = useState('')
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const { data: labels = [] } = useQuery({ queryKey: ['labels'], queryFn: api.listLabels })

  const query = text.trim()
  const options: Option[] = []
  if (query) {
    const needle = query.toLocaleLowerCase()
    for (const label of labels) {
      if (
        label.name.toLocaleLowerCase().includes(needle) &&
        !value.some((name) => same(name, label.name))
      ) {
        options.push({ kind: 'existing', name: label.name })
      }
    }
    const exists =
      labels.some((label) => same(label.name, query)) || value.some((name) => same(name, query))
    if (!exists) options.push({ kind: 'create', name: query })
  }
  const shown = open && options.length > 0

  const add = (name: string) => {
    if (!value.some((current) => same(current, name))) onChange([...value, name])
    setText('')
    setActive(0)
  }

  const remove = (name: string) => onChange(value.filter((current) => current !== name))

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter') {
      // Пустое поле отдаёт Enter форме — иначе слово не сохранить с клавиатуры
      if (!query) return
      event.preventDefault()
      const option = options[Math.min(active, options.length - 1)]
      if (option) add(option.name)
    } else if (event.key === 'Escape') {
      if (shown) event.preventDefault()
      setOpen(false)
    } else if (event.key === 'ArrowDown' && options.length) {
      event.preventDefault()
      setOpen(true)
      setActive((current) => (current + 1) % options.length)
    } else if (event.key === 'ArrowUp' && options.length) {
      event.preventDefault()
      setActive((current) => (current - 1 + options.length) % options.length)
    } else if (event.key === 'Backspace' && !text && value.length) {
      remove(value[value.length - 1])
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <span id={`${id}-label`} className="text-sm text-muted">
        Метки
      </span>
      <div className="relative">
        <div className="flex flex-wrap items-center gap-2 rounded border border-hairline px-3 py-2 focus-within:border-accent">
          {value.map((name) => (
            <span
              key={name}
              className="flex items-center gap-1 rounded bg-panel px-2 py-1 text-sm text-ink-soft"
            >
              {name}
              <button
                type="button"
                onClick={() => remove(name)}
                aria-label={`Снять метку «${name}»`}
                className="text-muted hover:text-wrong"
              >
                ×
              </button>
            </span>
          ))}
          <input
            value={text}
            onChange={(event) => {
              setText(event.target.value)
              setOpen(true)
              setActive(0)
            }}
            onFocus={() => setOpen(true)}
            onBlur={() => setOpen(false)}
            onKeyDown={onKeyDown}
            maxLength={LABEL_NAME_MAX}
            placeholder={value.length ? '' : 'Например, кухня'}
            autoComplete="off"
            role="combobox"
            aria-labelledby={`${id}-label`}
            aria-expanded={shown}
            aria-controls={`${id}-list`}
            className="min-w-32 flex-1 py-1 outline-none"
          />
        </div>

        {shown ? (
          <ul
            id={`${id}-list`}
            role="listbox"
            className="absolute z-10 mt-1 max-h-60 w-full overflow-y-auto rounded border border-hairline bg-white py-1 shadow-md"
          >
            {options.map((option, index) => (
              <li
                key={`${option.kind}:${option.name}`}
                role="option"
                aria-selected={index === active}
                // mousedown, а не click: иначе поле потеряет фокус и закроет список раньше
                onMouseDown={(event) => {
                  event.preventDefault()
                  add(option.name)
                }}
                onMouseEnter={() => setActive(index)}
                className={`cursor-pointer px-3 py-2 ${
                  index === active ? 'bg-panel text-ink' : 'text-ink-soft'
                }`}
              >
                {option.kind === 'create' ? `Создать метку «${option.name}»` : option.name}
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </div>
  )
}
