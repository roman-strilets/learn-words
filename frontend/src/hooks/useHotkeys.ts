import { useEffect, useRef } from 'react'

export type HotkeyMap = Record<string, (event: KeyboardEvent) => void>

/**
 * Физическая клавиша независимо от раскладки: `KeyA` → `a`, `Digit1` → `1`.
 *
 * `event.key` отдаёт символ текущей раскладки — в русской физическая «A» даёт
 * «ф», и сопоставление по символу перестаёт работать. `event.code` привязан к
 * позиции клавиши, поэтому английское слово можно набирать, не переключаясь.
 */
function physicalKey(code: string): string | null {
  if (code.length === 4 && code.startsWith('Key')) return code.slice(3).toLowerCase()
  if (code.length === 6 && code.startsWith('Digit')) return code.slice(5)
  if (code.length === 7 && code.startsWith('Numpad') && code[6] >= '0' && code[6] <= '9') {
    return code[6]
  }
  return null
}

/**
 * Горячие клавиши упражнений (Enter, Escape, цифры, буквы).
 *
 * Обработчики держим в ref: иначе каждый ререндер пересоздавал бы слушатель,
 * а на быстрых нажатиях это теряет события.
 */
export function useHotkeys(map: HotkeyMap, enabled = true) {
  const mapRef = useRef(map)
  mapRef.current = map

  useEffect(() => {
    if (!enabled) return

    const onKeyDown = (event: KeyboardEvent) => {
      const byChar = mapRef.current[event.key]
      if (byChar) {
        byChar(event)
        return
      }
      // Символ не подошёл — пробуем позицию клавиши (иная раскладка)
      const physical = event.code ? physicalKey(event.code) : null
      const byCode = physical ? mapRef.current[physical] : undefined
      if (byCode) byCode(event)
    }

    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [enabled])
}

/** Ввод идёт в текстовое поле — цифровые шорткаты нужно пропускать. */
export function isTypingTarget(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLInputElement ||
    target instanceof HTMLTextAreaElement ||
    (target instanceof HTMLElement && target.isContentEditable)
  )
}
