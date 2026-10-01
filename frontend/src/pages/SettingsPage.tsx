import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router'

import { api } from '../api/client'
import type { NewWordsOrder } from '../api/types'
import { ClassifierSection } from '../components/ClassifierSection'
import { LabelsSection } from '../components/LabelsSection'
import { ErrorBox, Spinner } from '../components/ui'
import { useSpeech, type VoiceOption } from '../speech/SpeechProvider'

/** Образец: одна и та же короткая фраза для всех голосов — их слышно сравнимо. */
const SAMPLE = 'This is how I sound.'

/**
 * Пункт списка с выбором одного варианта: так выглядят и порядок новых слов,
 * и голоса озвучки — «Системный голос» ничем не отличается от обычного.
 */
function OptionItem({
  label,
  note,
  active,
  onClick,
}: {
  label: string
  note?: string
  active: boolean
  onClick: () => void
}) {
  return (
    <li>
      <button
        type="button"
        onClick={onClick}
        aria-pressed={active}
        className={`flex w-full items-center justify-between gap-4 rounded-md border px-4 py-3 text-left transition-colors ${
          active
            ? 'border-accent bg-accent/5 font-semibold text-ink'
            : 'border-hairline text-ink-soft hover:border-muted'
        }`}
      >
        <span>{label}</span>
        {note ? <span className="text-sm font-normal text-muted">{note}</span> : null}
      </button>
    </li>
  )
}

const ORDERS: { value: NewWordsOrder; label: string; note?: string }[] = [
  { value: 'oldest_first', label: 'В порядке добавления', note: 'сначала давно добавленные' },
  { value: 'newest_first', label: 'Сначала недавно добавленные' },
]

/** Порядок новых слов хранится на сервере: слова отбирает он, а не браузер. */
function NewWordsOrderSection() {
  const queryClient = useQueryClient()
  const { data, isLoading, error } = useQuery({
    queryKey: ['settings'],
    queryFn: api.getSettings,
  })
  // Выбор уходит на сервер сразу, без кнопки «Сохранить»: вариантов два,
  // и промахнувшийся вернёт прежний одним нажатием
  const update = useMutation({
    mutationFn: api.updateSettings,
    onSuccess: (saved) => queryClient.setQueryData(['settings'], saved),
  })

  // Пока запрос в пути, отмечаем уже выбранный вариант, а не прежний
  const current = update.isPending ? update.variables.new_words_order : data?.new_words_order
  const failure = error ?? update.error

  return (
    <section className="flex flex-col gap-6">
      <h2 className="text-lg font-semibold text-ink-soft">Порядок новых слов</h2>
      <p className="text-muted">
        В каком порядке «Учить слова» берёт новые слова. Действует со следующего
        занятия; на «Повторить слова» не влияет — там слова идут по сроку.
      </p>

      {failure ? <ErrorBox message={failure.message} /> : null}

      {isLoading ? (
        <Spinner />
      ) : data ? (
        <ul className="flex flex-col gap-2">
          {ORDERS.map((order) => (
            <OptionItem
              key={order.value}
              label={order.label}
              note={order.note}
              active={current === order.value}
              onClick={() => update.mutate({ new_words_order: order.value })}
            />
          ))}
        </ul>
      ) : null}
    </section>
  )
}

function VoiceSection() {
  const { groups, selected, selectVoice, speakWith, error, supported } = useSpeech()

  /**
   * Выбрать голос и тут же произнести им образец.
   *
   * Образец идёт через `speakWith` с явным голосом, а не через `speak()`:
   * `selectVoice` меняет состояние асинхронно, и `speak()` в этом же
   * обработчике произнёс бы фразу предыдущим голосом.
   */
  const pick = (voice: VoiceOption | null) => {
    selectVoice(voice?.uri ?? null)
    speakWith(voice, SAMPLE)
  }

  return (
    <section className="flex flex-col gap-6">
      <h2 className="text-lg font-semibold text-ink-soft">Голос озвучки</h2>

      {!supported ? (
        // Синтеза речи нет вовсе — списка тоже нет: выбирать не из чего
        <p className="text-muted">
          Этот браузер не умеет произносить слова, поэтому озвучка недоступна и
          выбирать голос не из чего. Попробуйте Chrome, Safari или Firefox на
          компьютере.
        </p>
      ) : (
        <>
          {error ? <ErrorBox message={error} /> : null}

          <ul className="flex flex-col gap-2">
            {/* Первым пунктом — состояние «выбор не сделан»: к нему всегда
                можно вернуться, и оно же активно, когда сохранённый голос
                исчез из системы */}
            <OptionItem
              label="Системный голос"
              note="браузер подберёт сам"
              active={selected === null}
              onClick={() => pick(null)}
            />
          </ul>

          {groups.length === 0 ? (
            // Синтез есть, но английских голосов нет: «Системный голос» выше
            // остаётся рабочим, и пустоту нужно объяснить
            <p className="text-muted">
              Английских голосов в системе не нашлось — озвучивать будет тот,
              что подберёт браузер. Голоса устанавливает операционная система:
              на macOS — «Системные настройки» → «Универсальный доступ» →
              «Речь», на Windows — «Параметры» → «Время и язык» → «Речь».
            </p>
          ) : (
            groups.map((group) => (
              <div key={group.lang} className="flex flex-col gap-2">
                <h3 className="text-sm text-muted">
                  {group.flag} {group.label}
                </h3>
                <ul className="flex flex-col gap-2">
                  {group.voices.map((voice: VoiceOption) => (
                    <OptionItem
                      key={voice.uri}
                      label={voice.name}
                      // Основной голос браузера помечен, но остаётся в своей
                      // группе: вытащить его наверх — сломать группировку
                      note={voice.isDefault ? 'основной голос браузера' : undefined}
                      active={selected?.uri === voice.uri}
                      onClick={() => pick(voice)}
                    />
                  ))}
                </ul>
              </div>
            ))
          )}
        </>
      )}
    </section>
  )
}

const TABS = [
  { value: 'general', label: 'Общие' },
  { value: 'labels', label: 'Метки' },
  { value: 'classifier', label: 'Разметка' },
] as const

type Tab = (typeof TABS)[number]['value']

export function SettingsPage() {
  // Вкладка в адресе, а не в `localStorage`: это навигация, а не предпочтение —
  // ссылка ведёт прямо на неё, и перезагрузка её не теряет
  const [params, setParams] = useSearchParams()
  const tab: Tab = TABS.find((item) => item.value === params.get('tab'))?.value ?? 'general'

  return (
    <div className="flex w-full max-w-3xl flex-col gap-8">
      <h1 className="text-4xl font-bold text-ink">Настройки</h1>

      <div role="tablist" className="flex gap-2 border-b border-hairline">
        {TABS.map((item) => (
          <button
            key={item.value}
            type="button"
            role="tab"
            aria-selected={tab === item.value}
            onClick={() => setParams(item.value === 'general' ? {} : { tab: item.value })}
            className={`-mb-px border-b-2 px-4 py-2 transition-colors ${
              tab === item.value
                ? 'border-accent font-semibold text-ink'
                : 'border-transparent text-muted hover:text-ink'
            }`}
          >
            {item.label}
          </button>
        ))}
      </div>

      {tab === 'labels' ? (
        <LabelsSection />
      ) : tab === 'classifier' ? (
        <ClassifierSection />
      ) : (
        <>
          <NewWordsOrderSection />
          <VoiceSection />
        </>
      )}
    </div>
  )
}
