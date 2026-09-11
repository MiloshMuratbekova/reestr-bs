import { value } from './ui.jsx'

/** Метки риска для отбора списков.
 *
 * Перечень повторяет реестры, по которым строится портрет лица. Метки
 * не взаимоисключающие: выбрав несколько, получаем всех, кто попал хотя бы
 * в один из списков.
 */
export const RISK_OPTIONS = [
  ['erdr', 'ЕРДР'],
  ['invalid', 'Инвалид'],
  ['debtor', 'Должник'],
  ['pdl', 'ПДЛ'],
  ['ludoman', 'Лудоман'],
  ['forbes', 'ФОРБС'],
  ['wanted', 'В розыске'],
  ['suspect', 'Подозреваемый'],
  ['custody', 'Под стражей'],
  ['prisoner', 'Сиделец'],
  ['selflimit', 'Самоограничение'],
]

export default function RiskFilter({ selected, onChange }) {
  const chosen = new Set(selected || [])

  const toggle = (key) => {
    const next = new Set(chosen)
    if (next.has(key)) next.delete(key)
    else next.add(key)
    onChange([...next])
  }

  return (
    <div>
      <div className="mb-1 flex items-center justify-between">
        <span className="label mb-0">Метки риска</span>
        {chosen.size > 0 && (
          <button
            type="button"
            className="text-xs text-afm-700 hover:underline"
            onClick={() => onChange([])}
          >
            снять все
          </button>
        )}
      </div>
      <div className="flex flex-wrap gap-1">
        {RISK_OPTIONS.map(([key, label]) => (
          <button
            key={key}
            type="button"
            onClick={() => toggle(key)}
            className={`badge ${
              chosen.has(key)
                ? 'bg-amber-100 text-amber-900 ring-1 ring-amber-300'
                : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
            }`}
          >
            {value(label)}
          </button>
        ))}
      </div>
      {chosen.size > 1 && (
        <p className="mt-1 text-[11px] text-slate-400">
          Показываются попавшие хотя бы в один из выбранных списков
        </p>
      )}
    </div>
  )
}
