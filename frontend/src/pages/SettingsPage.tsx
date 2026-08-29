import { ErrorBox } from '../components/ui'
import { useSpeech, type VoiceOption } from '../speech/SpeechProvider'

/** Образец: одна и та же короткая фраза для всех голосов — их слышно сравнимо. */
const SAMPLE = 'This is how I sound.'

/** Пункт списка: «Системный голос» и обычный голос выглядят одинаково. */
function VoiceItem({
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

export function SettingsPage() {
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
    <div className="flex w-full max-w-3xl flex-col gap-8">
      <h1 className="text-4xl font-bold text-ink">Настройки</h1>

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
              <VoiceItem
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
                      <VoiceItem
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
    </div>
  )
}
