import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'

import { useLocalStorage } from '../hooks/useLocalStorage'

/** Аватарки голосов — как в списке Kate / Robot / Charlotte на макете. */
const VOICE_EMOJI = ['👩', '🤖', '👧', '🧑', '👨', '👴', '👩‍🦰', '🧔', '👱']

const FLAG_BY_LANG: Record<string, string> = {
  'en-US': '🇺🇸',
  'en-GB': '🇬🇧',
  'en-AU': '🇦🇺',
  'en-CA': '🇨🇦',
  'en-IE': '🇮🇪',
  'en-IN': '🇮🇳',
  'en-NZ': '🇳🇿',
  'en-ZA': '🇿🇦',
}

export interface VoiceOption {
  uri: string
  name: string
  lang: string
  emoji: string
  flag: string
  voice: SpeechSynthesisVoice
}

interface SpeechContextValue {
  voices: VoiceOption[]
  selected: VoiceOption | null
  selectVoice: (uri: string) => void
  speak: (text: string) => void
  rate: number
  setRate: (rate: number) => void
  autoplay: boolean
  setAutoplay: (value: boolean) => void
  supported: boolean
}

const SpeechContext = createContext<SpeechContextValue | null>(null)

const MAX_VOICES = 9

function buildUtterance(
  text: string,
  voice: SpeechSynthesisVoice | null,
  rate: number,
): SpeechSynthesisUtterance {
  const utterance = new SpeechSynthesisUtterance(text)
  if (voice) {
    utterance.voice = voice
    utterance.lang = voice.lang
  } else {
    // Без явного голоса браузер сам подберёт системный для этого языка
    utterance.lang = 'en-US'
  }
  utterance.rate = rate
  return utterance
}

export function SpeechProvider({ children }: { children: ReactNode }) {
  const [voices, setVoices] = useState<VoiceOption[]>([])
  const [selectedUri, setSelectedUri] = useLocalStorage<string | null>(
    'speech.voice',
    null,
  )
  const [rate, setRate] = useLocalStorage<number>('speech.rate', 1)
  const [autoplay, setAutoplay] = useLocalStorage<boolean>('speech.autoplay', true)

  useEffect(() => {
    const synth = window.speechSynthesis
    if (!synth) return

    // Очередь синтеза переживает перезагрузку вкладки. Если прошлая фраза
    // осталась в ней подвешенной, движок не начнёт ни одной следующей:
    // speaking навсегда true, события start и error не приходят, звука нет.
    // Разовый сброс на старте — единственный способ выйти из этого состояния.
    synth.cancel()

    // Список голосов в Chrome приходит асинхронно: разовый getVoices()
    // на монтировании вернул бы пустой массив.
    const load = () => {
      const english = synth
        .getVoices()
        .filter((voice) => voice.lang.toLowerCase().startsWith('en'))
        // Голос, выбранный браузером по умолчанию, ставим под цифру 1
        .sort((a, b) => Number(b.default) - Number(a.default))
        .slice(0, MAX_VOICES)
        .map((voice, index) => ({
          uri: voice.voiceURI,
          name: voice.name.replace(/\s*\(.*\)\s*$/, ''),
          lang: voice.lang,
          emoji: VOICE_EMOJI[index % VOICE_EMOJI.length],
          flag: FLAG_BY_LANG[voice.lang] ?? '🌐',
          voice,
        }))
      setVoices(english)
    }

    load()
    synth.addEventListener('voiceschanged', load)
    return () => synth.removeEventListener('voiceschanged', load)
  }, [])

  /**
   * Снять запрет на озвучку.
   *
   * Chrome отвечает `not-allowed`, пока в документе не было жеста
   * пользователя, — под запрет попадает и озвучка первой карточки, которая
   * заводится из эффекта. Беззвучная фраза на первом же клике или нажатии
   * клавиши ничего не произносит, но помечает движок разрешённым.
   */
  useEffect(() => {
    const synth = window.speechSynthesis
    if (!synth) return

    const unlock = () => {
      const primer = new SpeechSynthesisUtterance(' ')
      primer.volume = 0
      synth.speak(primer)
      stop()
    }
    const stop = () => {
      window.removeEventListener('pointerdown', unlock)
      window.removeEventListener('keydown', unlock)
    }

    window.addEventListener('pointerdown', unlock)
    window.addEventListener('keydown', unlock)
    return stop
  }, [])

  /**
   * Голос, выбранный пользователем осознанно.
   *
   * Без выбора голос не навязываем: `getVoices()[0]` вполне может оказаться
   * неработающим — сетевые голоса Google молчат без доступа к сети, системные
   * голоса macOS — пока не скачаны. Навязав такой, приложение теряет звук
   * целиком, хотя браузер сам по `lang` подобрал бы рабочий.
   */
  const chosen = useMemo(
    () => voices.find((voice) => voice.uri === selectedUri) ?? null,
    [voices, selectedUri],
  )

  // Для списка голосов: какой показывать активным, пока выбора не было
  const selected = useMemo(() => chosen ?? voices[0] ?? null, [chosen, voices])

  /**
   * Озвучить слово. Вызов синхронный: браузер связывает речь с жестом
   * пользователя, и перенос `speak()` в таймер способен её заблокировать.
   */
  const speak = useCallback(
    (text: string) => {
      const synth = window.speechSynthesis
      if (!synth || !text) return

      // Обрываем только то, что реально звучит. Безусловный `cancel()` — тот
      // самый известный баг Chrome: если он приходит, пока движок ещё заводит
      // фразу, очередь остаётся в паузе и больше не произносится ничего.
      if (synth.speaking || synth.pending) synth.cancel()
      // Из этой паузы движок вытаскивает только resume(), даже если на неё
      // никто не переводил осознанно.
      if (synth.paused) synth.resume()

      const voice = chosen?.voice ?? null
      const utterance = buildUtterance(text, voice, rate)
      utterance.onerror = (event) => {
        // Собственный cancel() тоже приходит сюда — это не отказ
        if (event.error === 'canceled' || event.error === 'interrupted') return

        // Молчание без объяснений — худший исход: называем причину вслух
        if (event.error === 'not-allowed') {
          console.error(
            'Озвучку запретил браузер (not-allowed). Проверьте, что вкладка не ' +
              'заглушена, а в настройках сайта разрешён звук.',
          )
          return
        }
        console.error(
          `Озвучка не удалась (${event.error}), голос: ${voice?.name ?? 'системный'}`,
        )
        // Отказать мог именно выбранный голос — пробуем системный
        if (voice) synth.speak(buildUtterance(text, null, rate))
      }
      synth.speak(utterance)
    },
    [chosen, rate],
  )

  const value = useMemo<SpeechContextValue>(
    () => ({
      voices,
      selected,
      selectVoice: setSelectedUri,
      speak,
      rate,
      setRate,
      autoplay,
      setAutoplay,
      supported: typeof window !== 'undefined' && 'speechSynthesis' in window,
    }),
    [voices, selected, setSelectedUri, speak, rate, setRate, autoplay, setAutoplay],
  )

  return <SpeechContext.Provider value={value}>{children}</SpeechContext.Provider>
}

export function useSpeech(): SpeechContextValue {
  const context = useContext(SpeechContext)
  if (!context) throw new Error('useSpeech должен вызываться внутри SpeechProvider')
  return context
}

/**
 * Произнести текст один раз при появлении карточки.
 *
 * `speak()` обрывает предыдущую фразу, а эффекты в StrictMode вызываются
 * дважды: без этой защиты второе срабатывание глушило первое и карточка
 * молчала. Кнопка «произнести» идёт мимо хука — там повтор как раз нужен.
 */
export function useSpeakOnce(text: string, enabled = true): void {
  const { speak } = useSpeech()
  const spoken = useRef<string | null>(null)

  useEffect(() => {
    if (!enabled || !text) return
    if (spoken.current === text) return
    spoken.current = text
    speak(text)
  }, [text, enabled, speak])
}
