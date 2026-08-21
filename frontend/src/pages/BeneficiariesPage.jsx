import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { errorMessage, listingApi } from '../api/client.js'
import {
  AlgorithmChips,
  EmptyState,
  ErrorMessage,
  Loading,
  Pagination,
  PageHeader,
  SortHeader,
  StatusBadge,
  TableSkeleton,
  number,
  riskStyle,
  value,
} from '../components/ui.jsx'

const PAGE_SIZE = 50

const ALGORITHM_OPTIONS = [
  'БС-1', 'БС-2', 'БС-3', 'БС-4', 'БС-6', 'БС-7', 'БС-8',
  'БС-9', 'БС-10', 'БС-11', 'БС-13', 'БС-16', 'БС-17', 'БС-22',
]

/** Боковая панель с профилем бенефициара и всеми его компаниями. */
function ProfilePanel({ iin, onClose }) {
  const navigate = useNavigate()
  const [profile, setProfile] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!iin) return undefined
    let cancelled = false
    setLoading(true)
    setError('')
    listingApi
      .beneficiary(iin)
      .then(({ data }) => {
        if (!cancelled) setProfile(data)
      })
      .catch((err) => {
        if (!cancelled) setError(errorMessage(err, 'Профиль не загружен'))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [iin])

  if (!iin) return null

  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      <div
        className="absolute inset-0 bg-slate-900/30"
        onClick={onClose}
        role="presentation"
      />
      <div className="relative flex h-full w-full max-w-2xl flex-col bg-white shadow-xl">
        <div className="flex items-start justify-between border-b border-slate-200 px-6 py-4">
          <div className="min-w-0">
            <div className="text-sm font-semibold text-slate-800">
              {value(profile?.benefeciary_name)}
            </div>
            <div className="font-mono text-xs text-slate-500">{value(iin)}</div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
            aria-label="Закрыть"
          >
            ✕
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-4">
          {loading && <Loading text="Загрузка профиля…" />}
          {error && <ErrorMessage message={error} />}

          {!loading && profile && (
            <>
              <div className="mb-4 grid grid-cols-2 gap-3">
                <div className="rounded-md bg-slate-50 px-4 py-3">
                  <div className="text-xs uppercase tracking-wide text-slate-500">Компаний</div>
                  <div className="mt-1 text-xl font-semibold text-slate-800">
                    {number(profile.company_count)}
                  </div>
                </div>
                <div className="rounded-md bg-slate-50 px-4 py-3">
                  <div className="text-xs uppercase tracking-wide text-slate-500">
                    Макс. вероятность
                  </div>
                  <div
                    className={`mt-1 text-xl font-semibold ${riskStyle(profile.max_ball3).text}`}
                  >
                    {Number(profile.max_ball3 || 0).toFixed(2)}%
                  </div>
                </div>
              </div>

              <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                Компании, где выявлен бенефициаром
              </div>

              {profile.companies?.length ? (
                <div className="space-y-2">
                  {profile.companies.map((row) => {
                    const style = riskStyle(row.ball3)
                    return (
                      <button
                        key={`${row.taxpayer_iin_bin}-${row.algorithms}`}
                        type="button"
                        onClick={() =>
                          navigate(`/company/${encodeURIComponent(row.taxpayer_iin_bin)}`)
                        }
                        className="w-full rounded-md border border-slate-200 px-4 py-3 text-left transition-colors hover:bg-slate-50"
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <div className="truncate text-sm font-medium text-slate-800">
                              {value(row.taxpayer_name)}
                            </div>
                            <div className="font-mono text-xs text-slate-500">
                              {value(row.taxpayer_iin_bin)}
                            </div>
                          </div>
                          <div className={`shrink-0 text-sm font-semibold ${style.text}`}>
                            {Number(row.ball3 || 0).toFixed(2)}%
                          </div>
                        </div>
                        <div className="mt-2 flex flex-wrap items-center gap-2">
                          <StatusBadge status={row.status} />
                          <AlgorithmChips codes={row.algorithm_codes} />
                        </div>
                        {row.dop_info && (
                          <div className="mt-2 line-clamp-2 text-xs text-slate-500">
                            {row.dop_info}
                          </div>
                        )}
                      </button>
                    )
                  })}
                </div>
              ) : (
                <EmptyState title="Компании не найдены" />
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}

export default function BeneficiariesPage() {
  const [searchParams, setSearchParams] = useSearchParams()

  const [filters, setFilters] = useState({
    query: searchParams.get('query') || '',
    status: searchParams.get('status') || '',
    algorithm: searchParams.get('algorithm') || '',
    risk: searchParams.get('risk') || '',
    nonresident: searchParams.get('nonresident') || '',
  })
  const [page, setPage] = useState(Number(searchParams.get('page')) || 1)
  const [sort, setSort] = useState(searchParams.get('sort') || 'max_ball3')
  const [order, setOrder] = useState(searchParams.get('order') || 'desc')

  const [data, setData] = useState({ items: [], total: 0 })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const { data: payload } = await listingApi.beneficiaries({
        page,
        limit: PAGE_SIZE,
        query: filters.query || undefined,
        status: filters.status || undefined,
        algorithm: filters.algorithm || undefined,
        risk: filters.risk || undefined,
        nonresident: filters.nonresident === '' ? undefined : filters.nonresident === 'yes',
        sort,
        order,
      })
      setData(payload)
    } catch (err) {
      setError(errorMessage(err, 'Не удалось получить список бенефициаров'))
      setData({ items: [], total: 0 })
    } finally {
      setLoading(false)
    }
  }, [filters, page, sort, order])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    const next = {}
    Object.entries({ ...filters, page, sort, order }).forEach(([key, item]) => {
      if (item && !(key === 'page' && item === 1)) next[key] = String(item)
    })
    setSearchParams(next, { replace: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters, page, sort, order])

  const changeFilter = (key, item) => {
    setFilters((current) => ({ ...current, [key]: item }))
    setPage(1)
  }

  const handleSort = (column) => {
    if (sort === column) {
      setOrder((current) => (current === 'asc' ? 'desc' : 'asc'))
    } else {
      setSort(column)
      setOrder('desc')
    }
    setPage(1)
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="Список бенефициарных собственников"
        description="Реестр в разрезе физических лиц: по одной строке на ИИН"
      />

      <div className="card p-4">
        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-5">
          <div className="lg:col-span-2">
            <label className="label" htmlFor="query">
              ИИН или ФИО
            </label>
            <input
              id="query"
              className="input"
              value={filters.query}
              onChange={(event) => changeFilter('query', event.target.value)}
              placeholder="Например: Иванов"
            />
          </div>

          <div>
            <label className="label" htmlFor="status">
              Статус
            </label>
            <select
              id="status"
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
            <label className="label" htmlFor="algorithm">
              Алгоритм
            </label>
            <select
              id="algorithm"
              className="input"
              value={filters.algorithm}
              onChange={(event) => changeFilter('algorithm', event.target.value)}
            >
              <option value="">Любой</option>
              {ALGORITHM_OPTIONS.map((code) => (
                <option key={code} value={code}>
                  {code}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="label" htmlFor="risk">
              Уровень риска
            </label>
            <select
              id="risk"
              className="input"
              value={filters.risk}
              onChange={(event) => changeFilter('risk', event.target.value)}
            >
              <option value="">Любой</option>
              <option value="high">Высокий (свыше 70%)</option>
              <option value="medium">Средний (40–70%)</option>
              <option value="low">Низкий (до 40%)</option>
            </select>
          </div>
        </div>

        <div className="mt-3 border-t border-slate-100 pt-3">
          <label className="label" htmlFor="nonresident">
            Резидентство
          </label>
          <select
            id="nonresident"
            className="input w-full md:w-64"
            value={filters.nonresident}
            onChange={(event) => changeFilter('nonresident', event.target.value)}
          >
            <option value="">Все</option>
            <option value="yes">Только нерезиденты</option>
            <option value="no">Только резиденты</option>
          </select>
        </div>
      </div>

      {error && <ErrorMessage message={error} onRetry={load} />}

      {loading ? (
        <TableSkeleton rows={10} columns={6} />
      ) : data.items.length === 0 ? (
        <EmptyState
          title="Ничего не найдено"
          description="Измените условия отбора"
        />
      ) : (
        <div className="card">
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <SortHeader
                    column="benefeciary_name"
                    label="ФИО"
                    sort={sort}
                    order={order}
                    onSort={handleSort}
                  />
                  <SortHeader
                    column="benefeciary_iin_bin"
                    label="ИИН"
                    sort={sort}
                    order={order}
                    onSort={handleSort}
                  />
                  <SortHeader
                    column="status"
                    label="Статус"
                    sort={sort}
                    order={order}
                    onSort={handleSort}
                  />
                  <th>Алгоритмы</th>
                  <SortHeader
                    column="company_count"
                    label="Компаний"
                    sort={sort}
                    order={order}
                    onSort={handleSort}
                    className="text-right"
                  />
                  <SortHeader
                    column="max_ball3"
                    label="Вероятность"
                    sort={sort}
                    order={order}
                    onSort={handleSort}
                  />
                  <th className="text-center">Нерезидент</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((item) => {
                  const style = riskStyle(item.max_ball3)
                  return (
                    <tr
                      key={item.benefeciary_iin_bin}
                      className="cursor-pointer"
                      onClick={() => setSelected(item.benefeciary_iin_bin)}
                    >
                      <td className="font-medium text-slate-800">
                        {value(item.benefeciary_name)}
                      </td>
                      <td className="whitespace-nowrap font-mono text-xs">
                        {value(item.benefeciary_iin_bin)}
                      </td>
                      <td>
                        <StatusBadge status={item.status} />
                      </td>
                      <td>
                        <AlgorithmChips codes={item.algorithm_codes} />
                      </td>
                      <td className="text-right font-semibold">{number(item.company_count)}</td>
                      <td className="w-44">
                        <div className={`mb-1 text-xs font-semibold ${style.text}`}>
                          {Number(item.max_ball3 || 0).toFixed(2)}%
                        </div>
                        <div className="h-2 overflow-hidden rounded-full bg-slate-200">
                          <div
                            className={`h-full rounded-full ${style.bar}`}
                            style={{ width: `${Math.min(100, Number(item.max_ball3) || 0)}%` }}
                          />
                        </div>
                      </td>
                      <td className="text-center">{item.is_nonresident ? '🌐' : ''}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          <Pagination
            page={page}
            limit={data.limit || PAGE_SIZE}
            total={data.total}
            onPage={setPage}
          />
        </div>
      )}

      <ProfilePanel iin={selected} onClose={() => setSelected('')} />
    </div>
  )
}
