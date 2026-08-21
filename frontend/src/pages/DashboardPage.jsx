import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { errorMessage, registryApi } from '../api/client.js'
import { BarChart, DonutChart, StatCard } from '../components/charts.jsx'
import {
  CardSkeleton,
  EmptyState,
  ErrorMessage,
  PageHeader,
  StatCardSkeleton,
  TableSkeleton,
  number,
  riskStyle,
  value,
} from '../components/ui.jsx'

function TopTable({ title, rows, metric, onOpen }) {
  if (!rows?.length) {
    return (
      <div className="card">
        <div className="card-header">
          <span className="card-title">{title}</span>
        </div>
        <EmptyState title="Нет данных" description="Реестр ещё не рассчитан" />
      </div>
    )
  }

  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">{title}</span>
      </div>
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>Компания</th>
              <th className="w-24 text-right">БС</th>
              <th className="w-40">Вероятность</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const style = riskStyle(row.max_ball3)
              return (
                <tr
                  key={row.taxpayer_iin_bin}
                  className="cursor-pointer"
                  onClick={() => onOpen(row.taxpayer_iin_bin)}
                >
                  <td>
                    <div className="font-medium text-slate-800">{value(row.taxpayer_name)}</div>
                    <div className="font-mono text-xs text-slate-500">
                      {value(row.taxpayer_iin_bin)}
                    </div>
                  </td>
                  <td className="text-right font-semibold text-slate-800">
                    {number(row.beneficiary_count)}
                  </td>
                  <td>
                    <div className={`mb-1 text-xs font-semibold ${style.text}`}>
                      {Number(row.max_ball3 || 0).toFixed(2)}%
                    </div>
                    <div className="h-2 overflow-hidden rounded-full bg-slate-200">
                      <div
                        className={`h-full rounded-full ${style.bar}`}
                        style={{ width: `${Math.min(100, Number(row.max_ball3) || 0)}%` }}
                      />
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <div className="px-5 py-2 text-xs text-slate-400">
        Метрика сортировки: {metric}
      </div>
    </div>
  )
}

export default function DashboardPage() {
  const navigate = useNavigate()
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = () => {
    setLoading(true)
    setError('')
    registryApi
      .stats()
      .then(({ data }) => setStats(data))
      .catch((err) => setError(errorMessage(err, 'Не удалось получить статистику реестра')))
      .finally(() => setLoading(false))
  }

  useEffect(load, [])

  const openCompany = (bin) => navigate(`/company/${encodeURIComponent(bin)}`)

  const algorithmBars = (stats?.by_algorithm || []).map((row) => ({
    label: row.algorithm_code,
    title: row.name,
    value: Number(row.beneficiary_count) || 0,
  }))

  const statusSlices = [
    {
      label: 'Регистрационные',
      value: Number(stats?.registration_count) || 0,
      color: '#1f4d87',
    },
    {
      label: 'Предполагаемые',
      value: Number(stats?.assumed_count) || 0,
      color: '#d97706',
    },
  ]

  return (
    <div className="space-y-6">
      <PageHeader
        title="Дашборд"
        description="Сводные показатели реестра бенефициарных собственников"
      >
        <button type="button" className="btn-secondary" onClick={load} disabled={loading}>
          Обновить
        </button>
      </PageHeader>

      {error && <ErrorMessage message={error} onRetry={load} />}

      {loading ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <StatCardSkeleton key={index} />
          ))}
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard
            label="Всего юридических лиц"
            value={stats?.total_companies}
            hint="по справочнику ЮЛ"
          />
          <StatCard
            label="Из них с выявленными БС"
            value={stats?.companies_with_bs}
            hint={
              stats?.total_companies
                ? `${((100 * (stats.companies_with_bs || 0)) / stats.total_companies).toFixed(2)}% от всех ЮЛ`
                : undefined
            }
          />
          <StatCard
            label="Всего бенефициаров"
            value={stats?.beneficiary_count}
            hint={`нерезидентов: ${number(stats?.nonresident_count)}`}
          />
          <StatCard
            label="Компаний с высоким риском"
            value={stats?.high_risk_count}
            hint="вероятность выше 70%"
            tone="danger"
          />
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="card lg:col-span-2">
          <div className="card-header">
            <span className="card-title">Бенефициары по алгоритмам</span>
            <span className="text-xs text-slate-400">
              рассчитано алгоритмов: {number(stats?.algorithms_calculated)} из{' '}
              {number(stats?.algorithms_total)}
            </span>
          </div>
          <div className="p-5">
            {loading ? (
              <CardSkeleton lines={6} />
            ) : (
              <BarChart data={algorithmBars} />
            )}
          </div>
        </div>

        <div className="card">
          <div className="card-header">
            <span className="card-title">Статусы бенефициаров</span>
          </div>
          <div className="p-5">
            {loading ? <CardSkeleton lines={4} /> : <DonutChart data={statusSlices} />}
          </div>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {loading ? (
          <>
            <TableSkeleton rows={6} columns={3} />
            <TableSkeleton rows={6} columns={3} />
          </>
        ) : (
          <>
            <TopTable
              title="Топ-10 компаний по количеству бенефициаров"
              rows={stats?.top_by_beneficiaries}
              metric="количество бенефициарных собственников"
              onOpen={openCompany}
            />
            <TopTable
              title="Топ-10 компаний по уровню риска"
              rows={stats?.top_by_risk}
              metric="максимальная вероятность (ball3)"
              onOpen={openCompany}
            />
          </>
        )}
      </div>
    </div>
  )
}
