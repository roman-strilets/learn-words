import type { ButtonHTMLAttributes, ReactNode } from 'react'

import { BulbIcon, SpeakerIcon } from './icons'

type Variant = 'primary' | 'secondary' | 'ghost'

const VARIANTS: Record<Variant, string> = {
  primary: 'bg-accent text-white hover:bg-accent-hover',
  secondary: 'bg-neutral-btn text-white hover:bg-neutral-btn-hover',
  ghost: 'bg-transparent text-ink-soft hover:bg-hairline/50',
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  /** Подпись под кнопкой с горячей клавишей — как «Кнопка Enter» на макете */
  hotkeyLabel?: string
}

export function Button({
  variant = 'primary',
  hotkeyLabel,
  className = '',
  children,
  ...rest
}: ButtonProps) {
  const button = (
    <button
      className={`flex items-center justify-center gap-2 rounded-md px-8 py-4 text-lg font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${VARIANTS[variant]} ${className}`}
      {...rest}
    >
      {children}
    </button>
  )

  if (!hotkeyLabel) return button

  return (
    <div className="flex flex-col items-center gap-1">
      {button}
      <span
        className={`text-sm ${variant === 'primary' ? 'text-accent' : 'text-muted'}`}
      >
        {hotkeyLabel}
      </span>
    </div>
  )
}

export function IconButton({
  className = '',
  children,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      className={`flex size-12 items-center justify-center rounded-full border-2 transition-colors disabled:opacity-40 ${className}`}
      {...rest}
    >
      {children}
    </button>
  )
}

export function HintButton({
  active,
  onClick,
  title = 'Подсказка',
}: {
  active: boolean
  onClick: () => void
  title?: string
}) {
  return (
    <IconButton
      onClick={onClick}
      title={title}
      aria-pressed={active}
      className={
        active
          ? 'border-bulb bg-bulb text-white'
          : 'border-transparent bg-hairline text-white hover:bg-muted'
      }
    >
      <BulbIcon className="size-6" />
    </IconButton>
  )
}

export function SpeakButton({
  onClick,
  disabled,
  title = 'Произнести',
}: {
  onClick: () => void
  disabled?: boolean
  title?: string
}) {
  return (
    <IconButton
      onClick={onClick}
      disabled={disabled}
      title={title}
      className="border-correct text-correct hover:bg-correct-soft"
    >
      <SpeakerIcon className="size-6" />
    </IconButton>
  )
}

/** Поле формы словаря: подпись сверху, инпут во всю ширину. */
export function TextField({
  label,
  value,
  onChange,
  required,
  autoFocus,
  maxLength,
  className = '',
}: {
  label: string
  value: string
  onChange: (value: string) => void
  required?: boolean
  autoFocus?: boolean
  maxLength?: number
  className?: string
}) {
  return (
    <label className="flex flex-col gap-2">
      <span className="text-sm text-muted">
        {label}
        {required ? <span className="text-wrong"> *</span> : null}
      </span>
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        autoFocus={autoFocus}
        maxLength={maxLength}
        autoComplete="off"
        className={`w-full rounded border border-hairline px-4 py-3 outline-none focus:border-accent ${className}`}
      />
    </label>
  )
}

export function Prompt({
  children,
  hint,
  onHint,
  hintShown,
}: {
  children: ReactNode
  hint?: string | null
  onHint?: () => void
  hintShown?: boolean
}) {
  return (
    <div className="flex flex-col items-center gap-3">
      <div className="flex items-center justify-center gap-4">
        <h2 className="text-4xl font-bold text-ink">{children}</h2>
        {hint && onHint ? (
          <HintButton active={Boolean(hintShown)} onClick={onHint} />
        ) : null}
      </div>
      {hintShown && hint ? (
        <p className="text-lg text-ink-soft italic">{hint}</p>
      ) : null}
    </div>
  )
}

export function Caption({ children }: { children: ReactNode }) {
  return <p className="text-center text-lg text-muted">{children}</p>
}

export function Spinner({ label = 'Загрузка…' }: { label?: string }) {
  return (
    <div className="flex flex-col items-center gap-3 py-20 text-muted">
      <div className="size-8 animate-spin rounded-full border-3 border-hairline border-t-accent" />
      <span>{label}</span>
    </div>
  )
}

export function ErrorBox({ message }: { message: string }) {
  return (
    <div className="rounded-md border border-wrong bg-wrong-soft px-4 py-3 text-wrong">
      {message}
    </div>
  )
}
