/**
 * Общие элементы интерфейса.
 * Пустые значения по всей системе показываются прочерком.
 */

export const DASH = '—'

export function value(raw) {
  if (raw === null || raw === undefined) return DASH
  const text = String(raw).trim()
  return text === '' ? DASH : text
}

export function Spinner({ className = 'h-5 w-5' }) {
  return (
    <svg className={`animate-spin ${className}`} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle className="opacity-20" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path
        className="opacity-90"
        fill="currentColor"
        d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"
      />
    </svg>
  )
}

export function Loading({ text = 'Загрузка…' }) {
  return (
    <div className="flex items-center justify-center gap-3 py-12 text-slate-500">
      <Spinner className="h-6 w-6" />
      <span className="text-sm">{text}</span>
    </div>
  )
}

export function ErrorMessage({ message, onRetry }) {
  if (!message) return null
  return (
    <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
      <div className="flex items-start gap-2">
        <span aria-hidden="true">⚠</span>
        <div className="flex-1">
          <p>{message}</p>
          {onRetry && (
            <button type="button" onClick={onRetry} className="mt-2 underline hover:no-underline">
              Повторить
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

export function InfoMessage({ children, tone = 'info' }) {
  const tones = {
    info: 'border-afm-200 bg-afm-50 text-afm-800',
    warning: 'border-amber-200 bg-amber-50 text-amber-900',
    success: 'border-emerald-200 bg-emerald-50 text-emerald-900',
  }
  return (
    <div className={`rounded-md border px-4 py-3 text-sm ${tones[tone] || tones.info}`}>
      {children}
    </div>
  )
}

export function EmptyState({ title, description }) {
  return (
    <div className="py-12 text-center">
      <p className="text-sm font-medium text-slate-600">{title}</p>
      {description && <p className="mt-1 text-sm text-slate-400">{description}</p>}
    </div>
  )
}

/** Цветовая шкала вероятности: >70 — красный, 40–70 — жёлтый, <40 — зелёный. */
export function riskTone(ball3) {
  const score = Number(ball3) || 0
  if (score > 70) return 'high'
  if (score >= 40) return 'medium'
  return 'low'
}

const RISK_STYLES = {
  high: {
    card: 'border-red-300 bg-red-50',
    bar: 'bg-red-500',
    text: 'text-red-700',
    badge: 'bg-red-100 text-red-800',
    label: 'Высокая',
  },
  medium: {
    card: 'border-amber-300 bg-amber-50',
    bar: 'bg-amber-500',
    text: 'text-amber-700',
    badge: 'bg-amber-100 text-amber-800',
    label: 'Средняя',
  },
  low: {
    card: 'border-emerald-300 bg-emerald-50',
    bar: 'bg-emerald-500',
    text: 'text-emerald-700',
    badge: 'bg-emerald-100 text-emerald-800',
    label: 'Низкая',
  },
}

export function riskStyle(ball3) {
  return RISK_STYLES[riskTone(ball3)]
}

export function ProbabilityBar({ value: ball3, showLabel = true }) {
  const score = Math.max(0, Math.min(100, Number(ball3) || 0))
  const style = riskStyle(score)
  return (
    <div className="w-full">
      {showLabel && (
        <div className="mb-1 flex items-center justify-between text-xs">
          <span className="text-slate-500">Вероятность</span>
          <span className={`font-semibold ${style.text}`}>{score.toFixed(2)}%</span>
        </div>
      )}
      <div className="h-2 w-full overflow-hidden rounded-full bg-slate-200">
        <div
          className={`h-full rounded-full transition-all ${style.bar}`}
          style={{ width: `${score}%` }}
        />
      </div>
    </div>
  )
}

export function StatusBadge({ status }) {
  const text = String(status || '')
  const isRegistration = text.startsWith('Регистрационный')
  const isNonResident = text.includes('нерезидент')

  const className = isRegistration
    ? 'bg-afm-100 text-afm-800'
    : 'bg-violet-100 text-violet-800'

  return (
    <span className={`badge ${className}`} title={text}>
      {value(text)}
      {isNonResident && <span className="ml-1" aria-hidden="true">🌐</span>}
    </span>
  )
}

export function AlgorithmChips({ codes }) {
  const list = Array.isArray(codes) ? codes : codes ? [codes] : []
  if (!list.length) return <span className="text-slate-400">{DASH}</span>
  return (
    <div className="flex flex-wrap gap-1">
      {list.map((code) => (
        <span key={code} className="badge bg-slate-100 text-slate-700 font-mono">
          {code}
        </span>
      ))}
    </div>
  )
}

export function Field({ label, children }) {
  return (
    <div>
      <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</dt>
      <dd className="mt-0.5 text-sm text-slate-800 break-words">{children}</dd>
    </div>
  )
}
