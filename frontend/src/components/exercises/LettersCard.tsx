import { useEffect, useMemo, useState } from 'react'

import type { LettersExercise } from '../../api/types'
import { isTypingTarget, useHotkeys } from '../../hooks/useHotkeys'
import type { HotkeyMap } from '../../hooks/useHotkeys'
import { Caption, Prompt } from '../ui'
import type { ExerciseCardProps } from './types'

const TYPABLE = 'abcdefghijklmnopqrstuvwxyz0123456789'.split('')

interface Slot {
  /** Индекс символа в маске — нужен, чтобы собрать ответ обратно */
  maskIndex: number
  char: string | null
  /** Из какой плитки банка взята буква; null — введена с клавиатуры */
  tile: number | null
}

function buildSlots(mask: string): Slot[] {
  return mask
    .split('')
    .map((char, maskIndex) => ({ char, maskIndex }))
    .filter((item) => item.char === '_')
    .map((item) => ({ maskIndex: item.maskIndex, char: null, tile: null }))
}

function assemble(mask: string, slots: Slot[]): string {
  const byIndex = new Map(slots.map((slot) => [slot.maskIndex, slot.char]))
  return mask
    .split('')
    .map((char, index) => (char === '_' ? (byIndex.get(index) ?? '') : char))
    .join('')
}

export function LettersCard({
  exercise,
  onAnswer,
  locked,
}: ExerciseCardProps<LettersExercise>) {
  const [slots, setSlots] = useState<Slot[]>(() => buildSlots(exercise.mask))
  const [bankVisible, setBankVisible] = useState(exercise.show_letters)
  const [usedHint, setUsedHint] = useState(false)
  // Нонс, а не флаг: каждое новое отклонение должно перезапускать анимацию
  const [rejected, setRejected] = useState(0)

  useEffect(() => {
    setSlots(buildSlots(exercise.mask))
    setBankVisible(exercise.show_letters)
    setUsedHint(false)
    setRejected(0)
  }, [exercise.word_id, exercise.mask, exercise.show_letters])

  const usedTiles = useMemo(
    () => new Set(slots.map((slot) => slot.tile).filter((tile) => tile !== null)),
    [slots],
  )

  const place = (char: string, tile: number | null) => {
    setSlots((current) => {
      const index = current.findIndex((slot) => slot.char === null)
      if (index === -1) return current
      const next = current.slice()
      next[index] = { ...next[index], char, tile }
      return next
    })
  }

  const removeLast = () => {
    setSlots((current) => {
      const index = current.map((slot) => slot.char !== null).lastIndexOf(true)
      if (index === -1) return current
      const next = current.slice()
      next[index] = { ...next[index], char: null, tile: null }
      return next
    })
  }

  const typeLetter = (char: string) => {
    if (bankVisible) {
      // Пока банк на экране, буквы можно брать только из него
      const tile = exercise.letters.findIndex(
        (letter, index) => letter === char && !usedTiles.has(index),
      )
      if (tile === -1) {
        // Буквы нет в банке — показываем, что нажатие дошло, но не подходит
        setRejected((tick) => tick + 1)
        return
      }
      place(char, tile)
      return
    }
    place(char, null)
  }

  useEffect(() => {
    if (rejected === 0) return
    const timer = window.setTimeout(() => setRejected(0), 300)
    return () => window.clearTimeout(timer)
  }, [rejected])

  // Все ячейки заполнены — отправляем ответ, отдельной кнопки на макете нет
  const filled = slots.every((slot) => slot.char !== null)
  useEffect(() => {
    if (!filled || locked) return
    onAnswer({ answer: assemble(exercise.mask, slots), usedHint })
  }, [filled, locked, exercise.mask, slots, usedHint, onAnswer])

  const hotkeys: HotkeyMap = {
    Backspace: (event) => {
      if (isTypingTarget(event.target)) return
      event.preventDefault()
      removeLast()
    },
  }
  for (const key of TYPABLE) {
    hotkeys[key] = (event) => {
      if (isTypingTarget(event.target)) return
      if (event.metaKey || event.ctrlKey || event.altKey) return
      event.preventDefault()
      typeLetter(key.toUpperCase())
    }
    hotkeys[key.toUpperCase()] = hotkeys[key]
  }
  useHotkeys(hotkeys, !locked)

  // Куда попадёт следующая набранная буква
  const activeMaskIndex = slots.find((slot) => slot.char === null)?.maskIndex ?? -1

  return (
    <div className="flex w-full max-w-3xl flex-col items-center gap-8">
      <Caption>Впишите перевод слова</Caption>

      <Prompt hint={exercise.hint} hintShown={usedHint} onHint={() => setUsedHint(true)}>
        {exercise.prompt}
      </Prompt>

      <div className="flex w-full flex-wrap items-center justify-center gap-2 rounded bg-panel px-6 py-12">
        {exercise.mask.split('').map((char, index) =>
          char === '_' ? (
            <button
              key={index}
              type="button"
              disabled={locked}
              onClick={removeLast}
              className={`flex size-14 items-center justify-center bg-white text-2xl font-semibold text-ink ${
                index === activeMaskIndex ? 'ring-2 ring-accent' : ''
              }`}
            >
              {slots.find((slot) => slot.maskIndex === index)?.char ?? ''}
            </button>
          ) : (
            <span key={index} className="w-6 text-center text-2xl text-muted">
              {char === ' ' ? '' : char}
            </span>
          ),
        )}
      </div>

      {bankVisible ? (
        <div className={`flex flex-wrap justify-center gap-3 ${rejected ? 'nudge' : ''}`}>
          {exercise.letters.map((letter, index) => (
            <button
              key={`${letter}-${index}`}
              type="button"
              disabled={locked || usedTiles.has(index)}
              onClick={() => place(letter, index)}
              className="flex size-12 items-center justify-center bg-panel text-2xl text-ink transition-opacity hover:bg-hairline disabled:opacity-25"
            >
              {letter}
            </button>
          ))}
        </div>
      ) : (
        <p className="text-muted">Введите слово с клавиатуры</p>
      )}

      <p className="text-center text-sm text-muted">
        Вы можете выбирать буквы мышью или вводить их с клавиатуры —
        раскладка не важна
      </p>

      <div className="flex gap-3 text-accent">
        {bankVisible ? (
          <button
            type="button"
            className="underline decoration-dashed underline-offset-4"
            onClick={() => setBankVisible(false)}
          >
            Скрыть буквы
          </button>
        ) : null}
        <span className="text-muted">|</span>
        <button
          type="button"
          disabled={locked}
          className="underline decoration-dashed underline-offset-4 disabled:opacity-50"
          onClick={() => onAnswer({ answer: null, usedHint: true })}
        >
          Показать ответ
        </button>
      </div>
    </div>
  )
}
