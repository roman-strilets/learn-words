# Phase 1 — Contract: `SpeechContext`

HTTP-контракт этой фичей не меняется: новых эндпоинтов нет, `schemas.py` и
`frontend/src/api/types.ts` остаются как есть. Единственный контракт, который правится, —
внутренний: интерфейс `SpeechContextValue`, через который страницы и карточки получают
доступ к озвучке. Он описан здесь, потому что у него пять потребителей и одно
**ломающее** изменение.

Файл: `frontend/src/speech/SpeechProvider.tsx`.

## Текущие потребители

| Файл | Что берёт |
|---|---|
| `components/exercises/IntroCard.tsx` | `speak`, `autoplay`, `supported` |
| `components/exercises/ChoiceCard.tsx` | `speak`, `autoplay`, `supported` |
| `components/exercises/DictationCard.tsx` | `speak`, `supported` |
| `components/exercises/Feedback.tsx` | `speak`, `autoplay`, `supported` |
| `pages/WordsPage.tsx` | `speak`, `supported` |
| `components/VoicePicker.tsx` | `voices`, `selected`, `selectVoice` — **файл удаляется** |
| `pages/SettingsPage.tsx` | новый потребитель: `groups`, `selected`, `selectVoice`, `speakWith`, `supported`, `error` |

Ни один из пяти остающихся потребителей не читает `voices`, `selected`, `emoji` и `flag`.
Поэтому изменения ниже их не задевают — правится только провайдер, страница настроек и
удаляемый `VoicePicker`.

## Что остаётся без изменений

```ts
speak: (text: string) => void      // озвучить выбранным (или системным) голосом
rate: number
setRate: (rate: number) => void
autoplay: boolean
setAutoplay: (value: boolean) => void
supported: boolean
selectVoice: (uri: string | null) => void
```

`selectVoice` уже принимает `null` — им выбирается «Системный голос», отдельного метода
сброса не нужно.

## Что появляется

```ts
/** Голоса, разложенные по языковому варианту. Пустой массив = голосов нет. */
groups: VoiceGroup[]

/**
 * Произнести текст заданным голосом, минуя сохранённый выбор.
 * `null` — намеренно без явного голоса (системный).
 * Нужен для образца: setState асинхронен, и speak() сразу после selectVoice()
 * взял бы предыдущий голос.
 */
speakWith: (voice: VoiceOption | null, text: string) => void

/** Человекочитаемая причина последнего отказа озвучки; null — отказа не было. */
error: string | null
```

## Что меняется несовместимо

```ts
// БЫЛО
voices: VoiceOption[]          // не более 9 голосов
selected: VoiceOption | null   // chosen ?? voices[0] — подставляет первый голос

// СТАЛО
voices: VoiceOption[]          // все английские голоса, без ограничения
selected: VoiceOption | null   // строго chosen: null = «Системный голос»
```

**Почему это ломающее изменение**: `selected` меняет смысл. Раньше он отвечал на вопрос
«какой пункт подсветить», подставляя первый голос списка, когда выбора не было. Теперь
он отвечает на вопрос «какой голос выбран», и `null` — полноценный ответ, который
страница настроек показывает пунктом «Системный голос». Старая подмена сделала бы этот
пункт недостижимым: при отсутствии выбора подсвечивался бы первый голос списка, то есть
интерфейс утверждал бы выбор, которого нет (нарушение FR-003a и FR-007).

Единственный потребитель `selected` — удаляемый `VoicePicker`, поэтому смена смысла ни
на что за пределами фичи не влияет.

## Тип элемента списка

```ts
// БЫЛО
interface VoiceOption {
  uri: string
  name: string
  lang: string
  emoji: string   // аватарка по индексу — уходит
  flag: string    // переезжает на уровень группы
  voice: SpeechSynthesisVoice
}

// СТАЛО
interface VoiceOption {
  uri: string
  name: string
  lang: string
  isDefault: boolean            // основной голос браузера — показывается пометкой
  voice: SpeechSynthesisVoice
}

interface VoiceGroup {
  lang: string
  label: string                 // «Американский», «Британский», …
  flag: string                  // 🌐 для неизвестного варианта
  voices: VoiceOption[]         // отсортированы по name
}
```

## Инварианты

1. `speak()` и `speakWith()` синхронны относительно жеста пользователя: вызываются прямо
   в обработчике события, без таймеров и промежуточных промисов — иначе браузер вправе
   заблокировать речь.
2. `groups` — чистая функция от `voices`: одинаковый вход даёт одинаковый порядок групп
   и голосов внутри них.
3. `error` не выставляется на кодах `canceled` и `interrupted`: это собственный
   `cancel()` провайдера, а не отказ.
4. Отказ выбранного голоса не оставляет пользователя в тишине: провайдер повторяет фразу
   без явного голоса — поведение уже реализовано и сохраняется.
5. Провайдер остаётся единственным местом, которое обращается к `window.speechSynthesis`.
