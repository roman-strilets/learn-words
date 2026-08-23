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

  const selected = useMemo(
    () => voices.find((voice) => voice.uri === selectedUri) ?? voices[0] ?? null,
    [voices, selectedUri],
  )

  const timer = useRef<number | null>(null)

  useEffect(() => {
    return () => {
      if (timer.current !== null) window.clearTimeout(timer.current)
    }
  }, [])

  /**
   * Озвучить слово.
   *
   * Запрос откладывается на такт и склеивается с предыдущим: автопроигрывание
   * висит на `useEffect`, а в StrictMode эффекты срабатывают дважды. Два
   * `speak()` подряд означали `cancel()` ровно в тот момент, когда Chrome
   * только заводил первую фразу, — очередь подвисала и слово молчало совсем.
   */
  const speak = useCallback(
    (text: string) => {
      const synth = window.speechSynthesis
      if (!synth || !text) return

      if (timer.current !== null) window.clearTimeout(timer.current)
      timer.current = window.setTimeout(() => {
        timer.current = null
        // Обрываем только то, что уже звучит: лишний cancel() и есть та самая
        // гонка. Без него фразы копились бы в очереди и звучали с задержкой.
        if (synth.speaking || synth.pending) synth.cancel()

        const utterance = new SpeechSynthesisUtterance(text)
        if (selected) {
          utterance.voice = selected.voice
          utterance.lang = selected.lang
        } else {
          utterance.lang = 'en-US'
        }
        utterance.rate = rate
        synth.speak(utterance)
      }, 0)
    },
    [selected, rate],
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
