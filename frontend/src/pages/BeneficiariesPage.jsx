import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { errorMessage, listingApi } from '../api/client.js'
import RiskFilter from '../components/RiskFilter.jsx'
import BeneficiaryProfile from '../components/BeneficiaryProfile.jsx'
import { ALGORITHM_OPTIONS, ALGORITHM_TITLES } from '../algorithms.js'
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
  value,
} from '../components/ui.jsx'

const PAGE_SIZE = 50


/** Боковая панель с профилем бенефициара и всеми его компаниями. */

export default function BeneficiariesPage() {
  const [searchParams, setSearchParams] = useSearchParams()

  const [filters, setFilters] = useState({
    query: searchParams.get('query') || '',
    status: searchParams.get('status') || '',
    algorithm: searchParams.get('algorithm') || '',
    nonresident: searchParams.get('nonresident') || '',
  })
  // Метки риска держим списком: их можно выбрать сразу несколько
  const [risks, setRisks] = useState(searchParams.getAll('risks'))
  const [page, setPage] = useState(Number(searchParams.get('page')) || 1)
  const [sort, setSort] = useState(searchParams.get('sort') || 'priority')
  const [order, setOrder] = useState(searchParams.get('order') || 'asc')

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
        nonresident: filters.nonresident === '' ? undefined : filters.nonresident === 'yes',
        risks: risks.length ? risks : undefined,
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
  }, [filters, risks, page, sort, order])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    const next = {}
    if (risks.length) next.risks = risks
    Object.entries({ ...filters, page, sort, order }).forEach(([key, item]) => {
      if (item && !(key === 'page' && item === 1)) next[key] = String(item)
    })
    setSearchParams(next, { replace: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters, risks, page, sort, order])

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
                  {code} — {ALGORITHM_TITLES[code]}
                </option>
              ))}
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

        <div className="mt-3 border-t border-slate-100 pt-3">
          <RiskFilter
            selected={risks}
            onChange={(next) => {
              setRisks(next)
              setPage(1)
            }}
          />
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
                  <th className="text-center">Нерезидент</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((item) => {
                  return (
                    <tr
                      key={item.benefeciary_key || item.benefeciary_iin_bin}
                      className="cursor-pointer"
                      onClick={() =>
                        setSelected(item.benefeciary_key || item.benefeciary_iin_bin)
                      }
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

      <BeneficiaryProfile iin={selected} onClose={() => setSelected('')} />
    </div>
  )
}
