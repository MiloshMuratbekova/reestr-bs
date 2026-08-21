/**
 * Графики дашборда.
 *
 * Нарисованы на SVG вручную, без библиотеки построения диаграмм: контур
 * закрытый, а тянуть в образ пакет ради двух графиков — лишний вес и лишняя
 * зависимость, которую потом не обновить.
 */

import { useState } from 'react'
import { DASH } from './ui.jsx'

const PALETTE = ['#1f4d87', '#2b64a8', '#4d84c4', '#7fa9d8', '#b0cbe9']

/** Столбчатая диаграмма: по одному столбцу на алгоритм. */
export function BarChart({ data, valueKey = 'value', labelKey = 'label', height = 260 }) {
  const [hover, setHover] = useState(null)
  const items = Array.isArray(data) ? data : []

  if (!items.length) {
    return <div className="py-12 text-center text-sm text-slate-400">Нет данных для графика</div>
  }

  const maximum = Math.max(...items.map((item) => Number(item[valueKey]) || 0), 1)
  const barWidth = 100 / items.length
  const plotHeight = height - 46

  return (
    <div className="relative">
      <svg
        viewBox={`0 0 100 ${height}`}
        preserveAspectRatio="none"
        className="w-full"
        style={{ height }}
      >
        {/* Горизонтальные направляющие: четыре доли от максимума */}
        {[0, 0.25, 0.5, 0.75, 1].map((fraction) => (
          <line
            key={fraction}
            x1="0"
            x2="100"
            y1={10 + plotHeight * fraction}
            y2={10 + plotHeight * fraction}
            stroke="#e2e8f0"
            strokeWidth="0.5"
            vectorEffect="non-scaling-stroke"
          />
        ))}

        {items.map((item, index) => {
          const value = Number(item[valueKey]) || 0
          const barHeight = (value / maximum) * plotHeight
          const x = index * barWidth + barWidth * 0.18
          const width = barWidth * 0.64
          return (
            <rect
              key={item[labelKey] ?? index}
              x={x}
              y={10 + plotHeight - barHeight}
              width={width}
              height={Math.max(barHeight, value > 0 ? 1 : 0)}
              fill={hover === index ? '#1a3d6b' : '#2b64a8'}
              onMouseEnter={() => setHover(index)}
              onMouseLeave={() => setHover(null)}
            />
          )
        })}
      </svg>

      {/* Подписи осей выводятся обычным текстом: в растянутом по ширине SVG
          шрифт исказился бы вместе с координатами */}
      <div className="flex">
        {items.map((item, index) => (
          <div
            key={item[labelKey] ?? index}
            className="min-w-0 flex-1 text-center text-[10px] leading-tight text-slate-500"
            onMouseEnter={() => setHover(index)}
            onMouseLeave={() => setHover(null)}
          >
            <div className="truncate font-medium text-slate-700">
              {Number(item[valueKey]) || 0}
            </div>
            <div className="truncate">{item[labelKey]}</div>
          </div>
        ))}
      </div>

      {hover !== null && items[hover] && (
        <div className="mt-2 rounded-md bg-slate-800 px-3 py-1.5 text-xs text-white">
          {items[hover][labelKey]}
          {items[hover].title ? ` — ${items[hover].title}` : ''}: {items[hover][valueKey]}
        </div>
      )}
    </div>
  )
}

/** Круговая диаграмма с отверстием. */
export function DonutChart({ data, size = 200 }) {
  const items = (Array.isArray(data) ? data : []).filter((item) => Number(item.value) > 0)
  const total = items.reduce((sum, item) => sum + Number(item.value), 0)

  if (!total) {
    return <div className="py-12 text-center text-sm text-slate-400">Нет данных для графика</div>
  }

  const radius = 15.915 // длина окружности при таком радиусе равна 100
  let offset = 25 // сдвиг, чтобы первый сектор начинался сверху

  const segments = items.map((item, index) => {
    const percent = (Number(item.value) / total) * 100
    const segment = {
      ...item,
      percent,
      color: item.color || PALETTE[index % PALETTE.length],
      dash: `${percent} ${100 - percent}`,
      offset,
    }
    offset -= percent
    return segment
  })

  return (
    <div className="flex flex-wrap items-center justify-center gap-6">
      <svg viewBox="0 0 40 40" style={{ width: size, height: size }} className="shrink-0">
        <circle cx="20" cy="20" r={radius} fill="none" stroke="#f1f5f9" strokeWidth="6" />
        {segments.map((segment) => (
          <circle
            key={segment.label}
            cx="20"
            cy="20"
            r={radius}
            fill="none"
            stroke={segment.color}
            strokeWidth="6"
            strokeDasharray={segment.dash}
            strokeDashoffset={segment.offset}
          >
            <title>{`${segment.label}: ${segment.value}`}</title>
          </circle>
        ))}
        <text
          x="20"
          y="19"
          textAnchor="middle"
          className="fill-slate-800"
          style={{ fontSize: '4px', fontWeight: 600 }}
        >
          {total.toLocaleString('ru-RU')}
        </text>
        <text
          x="20"
          y="24"
          textAnchor="middle"
          className="fill-slate-400"
          style={{ fontSize: '2.6px' }}
        >
          всего
        </text>
      </svg>

      <ul className="space-y-2 text-sm">
        {segments.map((segment) => (
          <li key={segment.label} className="flex items-center gap-2">
            <span
              className="h-3 w-3 shrink-0 rounded-sm"
              style={{ backgroundColor: segment.color }}
            />
            <span className="text-slate-600">{segment.label}</span>
            <span className="font-medium text-slate-800">
              {Number(segment.value).toLocaleString('ru-RU')}
            </span>
            <span className="text-xs text-slate-400">{segment.percent.toFixed(1)}%</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

/** Карточка показателя дашборда. */
export function StatCard({ label, value, hint, tone = 'default' }) {
  const tones = {
    default: 'text-slate-800',
    danger: 'text-red-600',
    warning: 'text-amber-600',
    success: 'text-emerald-600',
  }
  return (
    <div className="card px-5 py-4">
      <div className="text-xs uppercase tracking-wide text-slate-500">{label}</div>
      <div className={`mt-1 text-2xl font-semibold ${tones[tone] || tones.default}`}>
        {value === null || value === undefined
          ? DASH
          : Number(value).toLocaleString('ru-RU')}
      </div>
      {hint && <div className="mt-1 text-xs text-slate-400">{hint}</div>}
    </div>
  )
}
