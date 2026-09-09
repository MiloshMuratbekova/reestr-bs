import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { errorMessage, registryApi } from '../api/client.js'
import { BarChart, DonutChart, StatCard } from '../components/charts.jsx'
import {
  CardSkeleton,
  EmptyState,
  ErrorMessage,
  InfoMessage,
  PageHeader,
  StatCardSkeleton,
  TableSkeleton,
  number,
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
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              return (
                <tr
                  key={row.taxpayer_key || row.taxpayer_iin_bin}
                  className="cursor-pointer"
                  onClick={() => onOpen(row.taxpayer_key || row.taxpayer_iin_bin)}
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

  // Выбранный срез держится в адресе страницы: так его можно сохранить
  // в закладки и переслать коллеге вместе со ссылкой
  const [searchParams, setSearchParams] = useSearchParams()
  const filters = {
    algorithm: searchParams.get('algorithm') || '',
    status: searchParams.get('status') || '',
    nonresident: searchParams.get('nonresident') || '',
    date_from: searchParams.get('date_from') || '',
    date_to: searchParams.get('date_to') || '',
  }
  const anyFilter = Object.values(filters).some(Boolean)

  const changeFilter = (key, val) => {
    const next = new URLSearchParams(searchParams)
    if (val) next.set(key, val)
    else next.delete(key)
    setSearchParams(next, { replace: true })
  }

  const load = () => {
    setLoading(true)
    setError('')
    registryApi
      .stats({
        algorithm: filters.algorithm || undefined,
        status: filters.status || undefined,
        nonresident: filters.nonresident || undefined,
        date_from: filters.date_from || undefined,
        date_to: filters.date_to || undefined,
      })
      .then(({ data }) => setStats(data))
      .catch((err) => setError(errorMessage(err, 'Не удалось получить статистику реестра')))
      .finally(() => setLoading(false))
  }

  useEffect(load, [searchParams])

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

      {/* Отбор применяется сразу ко всем показателям страницы: карточкам,
          графику и обеим таблицам. Иначе цифры считались бы по разным
          срезам и не сходились бы между собой. */}
      <section className="card">
        <div className="grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-5">
          <div>
            <label className="label" htmlFor="d-algorithm">
              Алгоритм
            </label>
            <select
              id="d-algorithm"
              className="input"
              value={filters.algorithm}
              onChange={(event) => changeFilter('algorithm', event.target.value)}
            >
              <option value="">Все</option>
              {(stats?.by_algorithm || []).map((row) => (
                <option key={row.algorithm_code} value={row.algorithm_code}>
                  {row.algorithm_code}
                  {row.name ? ` — ${row.name}` : ''}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="label" htmlFor="d-status">
              Тип БС
            </label>
            <select
              id="d-status"
              className="input"
              value={filters.status}
              onChange={(event) => changeFilter('status', event.target.value)}
            >
              <option value="">Любой</option>
              <option value="registration">Регистрационный</option>
              <option value="assumed">Предполагаемый</option>
            </select>
          </div>

          <div>
            <label className="label" htmlFor="d-nonresident">
              Резидентство
            </label>
            <select
              id="d-nonresident"
              className="input"
              value={filters.nonresident}
              onChange={(event) => changeFilter('nonresident', event.target.value)}
            >
              <option value="">Все</option>
              <option value="true">Только нерезиденты</option>
              <option value="false">Без нерезидентов</option>
            </select>
          </div>

          <div>
            <label className="label" htmlFor="d-from">
              Дата актуальности с
            </label>
            <input
              id="d-from"
              type="date"
              className="input"
              value={filters.date_from}
              onChange={(event) => changeFilter('date_from', event.target.value)}
            />
          </div>

          <div>
            <label className="label" htmlFor="d-to">
              по
            </label>
            <input
              id="d-to"
              type="date"
              className="input"
              value={filters.date_to}
              onChange={(event) => changeFilter('date_to', event.target.value)}
            />
          </div>
        </div>

        {anyFilter && (
          <div className="flex items-center justify-between border-t border-slate-100 px-4 py-3">
            <span className="text-xs text-slate-500">
              Показатели посчитаны по выбранному срезу
            </span>
            <button
              type="button"
              className="btn-secondary"
              onClick={() => setSearchParams(new URLSearchParams(), { replace: true })}
            >
              Сбросить отбор
            </button>
          </div>
        )}
      </section>

      {anyFilter && stats && stats.filters_supported === false && (
        <InfoMessage tone="warning">
          Отбор не применён: реестр собран по таблицам алгоритмов, а не по сводной
          таблице — полей для отбора там нет. Показатели приведены целиком.
        </InfoMessage>
      )}

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
            label="Компаний с регистрационным БС"
            value={stats?.registration_companies}
            hint={`только предполагаемые: ${number(stats?.assumed_companies)}`}
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
              title="Топ-10 компаний по силе признака"
              rows={stats?.top_by_priority}
              metric="балл приоритетности: чем меньше, тем надёжнее выявление"
              onOpen={openCompany}
            />
          </>
        )}
      </div>
    </div>
  )
}
