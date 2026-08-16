import { useCallback, useState } from 'react'

/** Состояние, переживающее перезагрузку страницы (выбор голоса, скорость речи). */
export function useLocalStorage<T>(key: string, initial: T) {
  const [value, setValue] = useState<T>(() => {
    try {
      const stored = window.localStorage.getItem(key)
      return stored === null ? initial : (JSON.parse(stored) as T)
    } catch {
      return initial
    }
  })

  const update = useCallback(
    (next: T) => {
      setValue(next)
      try {
        window.localStorage.setItem(key, JSON.stringify(next))
      } catch {
        /* приватный режим — просто теряем настройку */
      }
    },
    [key],
  )

  return [value, update] as const
}
