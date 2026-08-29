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

/**
 * Языковые варианты английского: флаг и русское название.
 *
 * Порядок записей задаёт порядок групп на странице настроек, поэтому карта —
 * Map, а не объект: у неё порядок ключей часть контракта, а не деталь движка.
 * Список заведомо неполный — браузеры отдают и редкие теги вроде `en-029`,
 * поэтому у незнакомого варианта есть запасной вид (🌐 и сам тег).
 */
const LANG_VARIANTS = new Map<string, { flag: string; label: string }>([
  ['en-US', { flag: '🇺🇸', label: 'Американский' }],
  ['en-GB', { flag: '🇬🇧', label: 'Британский' }],
  ['en-AU', { flag: '🇦🇺', label: 'Австралийский' }],
  ['en-CA', { flag: '🇨🇦', label: 'Канадский' }],
  ['en-IE', { flag: '🇮🇪', label: 'Ирландский' }],
  ['en-IN', { flag: '🇮🇳', label: 'Индийский' }],
  ['en-NZ', { flag: '🇳🇿', label: 'Новозеландский' }],
  ['en-ZA', { flag: '🇿🇦', label: 'Южноафриканский' }],
])

export interface VoiceOption {
  uri: string
  name: string
  lang: string
  /** Голос, который браузер считает основным: показывается пометкой */
  isDefault: boolean
  voice: SpeechSynthesisVoice
}

export interface VoiceGroup {
  lang: string
  label: string
  flag: string
  /** Голоса варианта, отсортированные по имени */
  voices: VoiceOption[]
}

interface SpeechContextValue {
  voices: VoiceOption[]
  groups: VoiceGroup[]
  selected: VoiceOption | null
  selectVoice: (uri: string | null) => void
  speak: (text: string) => void
  speakWith: (voice: VoiceOption | null, text: string) => void
  /** Человекочитаемая причина последнего отказа озвучки; null — отказа не было */
  error: string | null
  rate: number
  setRate: (rate: number) => void
  autoplay: boolean
  setAutoplay: (value: boolean) => void
  supported: boolean
}

const SpeechContext = createContext<SpeechContextValue | null>(null)

/**
 * Разложить голоса по языковому варианту.
 *
 * Чистая функция: одинаковый вход даёт одинаковый порядок групп и голосов
 * внутри них — голос не переезжает с места на место между открытиями страницы.
 */
function groupVoices(voices: VoiceOption[]): VoiceGroup[] {
  const byLang = new Map<string, VoiceOption[]>()
  for (const voice of voices) {
    const group = byLang.get(voice.lang)
    if (group) group.push(voice)
    else byLang.set(voice.lang, [voice])
  }

  // Известные варианты — в порядке карты, незнакомые теги следом по алфавиту
  const known = [...LANG_VARIANTS.keys()].filter((lang) => byLang.has(lang))
  const unknown = [...byLang.keys()].filter((lang) => !LANG_VARIANTS.has(lang)).sort()

  return [...known, ...unknown].map((lang) => {
    const variant = LANG_VARIANTS.get(lang)
    return {
      lang,
      label: variant?.label ?? lang,
      flag: variant?.flag ?? '🌐',
      voices: (byLang.get(lang) ?? []).sort((a, b) => a.name.localeCompare(b.name)),
    }
  })
}

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
  const [error, setError] = useState<string | null>(null)
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
      const seen = new Set<string>()
      const english: VoiceOption[] = []
      for (const voice of synth.getVoices()) {
        if (!voice.lang.toLowerCase().startsWith('en')) continue
        // Браузеры изредка отдают один голос дважды — оставляем первый
        if (seen.has(voice.voiceURI)) continue
        seen.add(voice.voiceURI)
        english.push({
          uri: voice.voiceURI,
          name: voice.name.replace(/\s*\(.*\)\s*$/, ''),
          lang: voice.lang,
          isDefault: voice.default,
          voice,
        })
      }
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

  const groups = useMemo(() => groupVoices(voices), [voices])

  /**
   * Голос, выбранный пользователем осознанно; `null` — «Системный голос».
   *
   * Без выбора голос не навязываем: `getVoices()[0]` вполне может оказаться
   * неработающим — сетевые голоса Google молчат без доступа к сети, системные
   * голоса macOS — пока не скачаны. Навязав такой, приложение теряет звук
   * целиком, хотя браузер сам по `lang` подобрал бы рабочий.
   *
   * Раньше для списка голосов отсюда отдавался `chosen ?? voices[0]`. Подмена
   * убрана: с ней пункт «Системный голос» никогда не был бы активным, а
   * интерфейс утверждал бы выбор, которого нет. Исчезнувший из системы голос
   * тоже даёт `null` — и список честно показывает системный голос.
   */
  const selected = useMemo(
    () => voices.find((voice) => voice.uri === selectedUri) ?? null,
    [voices, selectedUri],
  )

  /**
   * Произнести текст заданным голосом. Общее тело `speak` и `speakWith`:
   * обход зависшей очереди и разбор ошибок должны быть в одном месте.
   *
   * Вызов синхронный: браузер связывает речь с жестом пользователя, и перенос
   * `synth.speak()` в таймер способен её заблокировать.
   */
  const say = useCallback(
    (text: string, voice: SpeechSynthesisVoice | null) => {
      const synth = window.speechSynthesis
      if (!synth || !text) return

      // Обрываем только то, что реально звучит. Безусловный `cancel()` — тот
      // самый известный баг Chrome: если он приходит, пока движок ещё заводит
      // фразу, очередь остаётся в паузе и больше не произносится ничего.
      if (synth.speaking || synth.pending) synth.cancel()
      // Из этой паузы движок вытаскивает только resume(), даже если на неё
      // никто не переводил осознанно.
      if (synth.paused) synth.resume()

      const utterance = buildUtterance(text, voice, rate)
      // Заговорил — значит, прошлый отказ больше ничего не объясняет
      utterance.onstart = () => setError(null)
      utterance.onerror = (event) => {
        // Собственный cancel() тоже приходит сюда — это не отказ
        if (event.error === 'canceled' || event.error === 'interrupted') return

        // Молчание без объяснений — худший исход: называем причину и вслух,
        // и в интерфейсе: до консоли пользователь не дойдёт
        if (event.error === 'not-allowed') {
          const message =
            'Озвучку запретил браузер. Проверьте, что вкладка не заглушена, ' +
            'а в настройках сайта разрешён звук.'
          console.error(`${message} (not-allowed)`)
          setError(message)
          return
        }
        console.error(
          `Озвучка не удалась (${event.error}), голос: ${voice?.name ?? 'системный'}`,
        )
        setError(
          voice
            ? `Голос «${voice.name}» не произнёс фразу — озвучиваем системным. ` +
                'Выберите другой голос.'
            : `Озвучка не удалась (${event.error}).`,
        )
        // Отказать мог именно выбранный голос — пробуем системный.
        // Без onstart: запасная фраза звучит, но объяснение остаётся на виду,
        // иначе пользователь так и не узнает, почему выбранный голос молчит.
        if (voice) synth.speak(buildUtterance(text, null, rate))
      }
      synth.speak(utterance)
    },
    [rate],
  )

  /** Озвучить слово голосом, который выбран в настройках. */
  const speak = useCallback(
    (text: string) => say(text, selected?.voice ?? null),
    [say, selected],
  )

  /**
   * Произнести текст заданным голосом, минуя сохранённый выбор;
   * `null` — намеренно без явного голоса (системный).
   *
   * Нужен для образца на странице настроек: `setState` асинхронен, и `speak()`
   * сразу после `selectVoice()` в том же обработчике взял бы предыдущий голос —
   * пользователь щёлкнул бы по новому голосу, а услышал старый.
   */
  const speakWith = useCallback(
    (voice: VoiceOption | null, text: string) => say(text, voice?.voice ?? null),
    [say],
  )

  const value = useMemo<SpeechContextValue>(
    () => ({
      voices,
      groups,
      selected,
      selectVoice: setSelectedUri,
      speak,
      speakWith,
      error,
      rate,
      setRate,
      autoplay,
      setAutoplay,
      supported: typeof window !== 'undefined' && 'speechSynthesis' in window,
    }),
    [
      voices,
      groups,
      selected,
      setSelectedUri,
      speak,
      speakWith,
      error,
      rate,
      setRate,
      autoplay,
      setAutoplay,
    ],
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
