import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { errorMessage, listingApi, reportsApi, saveBlob } from '../api/client.js'
import { useAuth } from '../context/AuthContext.jsx'
import {
  EmptyState,
  ErrorMessage,
  InfoMessage,
  Pagination,
  PageHeader,
  SortHeader,
  Spinner,
  TableSkeleton,
  number,
  riskStyle,
  value,
} from '../components/ui.jsx'

const PAGE_SIZE = 50

export default function CompaniesPage() {
  const navigate = useNavigate()
  const { isAdministrator } = useAuth()
  const [searchParams, setSearchParams] = useSearchParams()

  const [filters, setFilters] = useState({
    query: searchParams.get('query') || '',
    region: searchParams.get('region') || '',
    ownership: searchParams.get('ownership') || '',
    risk: searchParams.get('risk') || '',
    scope: searchParams.get('scope') || 'registry',
  })
  const [page, setPage] = useState(Number(searchParams.get('page')) || 1)
  const [sort, setSort] = useState(searchParams.get('sort') || 'max_ball3')
  const [order, setOrder] = useState(searchParams.get('order') || 'desc')

  const [data, setData] = useState({ items: [], total: 0, scope: 'registry' })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const { data: payload } = await listingApi.companies({
        page,
        limit: PAGE_SIZE,
        query: filters.query || undefined,
        region: filters.region || undefined,
        ownership: filters.ownership || undefined,
        risk: filters.risk || undefined,
        scope: filters.scope,
        sort,
        order,
      })
      setData(payload)
    } catch (err) {
      setError(errorMessage(err, 'Не удалось получить список юридических лиц'))
      setData({ items: [], total: 0, scope: filters.scope })
    } finally {
      setLoading(false)
    }
  }, [filters, page, sort, order])

  useEffect(() => {
    load()
  }, [load])

  // Состояние страницы держится в адресе: ссылку можно передать коллеге,
  // а возврат из карточки компании не сбрасывает фильтры
  useEffect(() => {
    const next = {}
    Object.entries({ ...filters, page, sort, order }).forEach(([key, item]) => {
      if (item && !(key === 'page' && item === 1) && !(key === 'scope' && item === 'registry')) {
        next[key] = String(item)
      }
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

  const exportExcel = async () => {
    setExporting(true)
    setExportError('')
    try {
      const { data: report } = await reportsApi.generate('registry', 'xlsx', { limit: 20000 })
      const { data: blob } = await reportsApi.download(report.id)
      saveBlob(blob, report.file_name)
    } catch (err) {
      setExportError(errorMessage(err, 'Не удалось сформировать файл выгрузки'))
    } finally {
      setExporting(false)
    }
  }

  const dictionaryScope = filters.scope === 'all'

  return (
    <div className="space-y-4">
      <PageHeader
        title="Список юридических лиц"
        description="Компании с показателями реестра бенефициарных собственников"
      >
        {isAdministrator && (
          <button
            type="button"
            className="btn-secondary"
            onClick={exportExcel}
            disabled={exporting}
          >
            {exporting && <Spinner className="h-4 w-4" />}
            {exporting ? 'Формирование…' : 'Экспорт в Excel'}
          </button>
        )}
      </PageHeader>

      {exportError && <ErrorMessage message={exportError} />}

      <div className="card p-4">
        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-5">
          <div className="lg:col-span-2">
            <label className="label" htmlFor="query">
              БИН или наименование
            </label>
            <input
              id="query"
              className="input"
              value={filters.query}
              onChange={(event) => changeFilter('query', event.target.value)}
              placeholder="Например: 123456789012"
            />
          </div>

          <div>
            <label className="label" htmlFor="region">
              Регион (код НД)
            </label>
            <input
              id="region"
              className="input"
              value={filters.region}
              onChange={(event) => changeFilter('region', event.target.value)}
              placeholder="Например: 71"
            />
          </div>

          <div>
            <label className="label" htmlFor="ownership">
              Тип собственности
            </label>
            <select
              id="ownership"
              className="input"
              value={filters.ownership}
              onChange={(event) => changeFilter('ownership', event.target.value)}
              disabled={dictionaryScope}
            >
              <option value="">Любой</option>
              <option value="state">Государственная</option>
              <option value="private">Прочая</option>
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
              disabled={dictionaryScope}
            >
              <option value="">Любой</option>
              <option value="high">Высокий (свыше 70%)</option>
              <option value="medium">Средний (40–70%)</option>
              <option value="low">Низкий (до 40%)</option>
            </select>
          </div>
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-4 border-t border-slate-100 pt-3">
          <label className="flex items-center gap-2 text-sm text-slate-600">
            <input
              type="radio"
              name="scope"
              checked={filters.scope === 'registry'}
              onChange={() => changeFilter('scope', 'registry')}
            />
            Только компании с выявленными БС
          </label>
          <label className="flex items-center gap-2 text-sm text-slate-600">
            <input
              type="radio"
              name="scope"
              checked={filters.scope === 'all'}
              onChange={() => changeFilter('scope', 'all')}
            />
            Все ЮЛ из справочника
          </label>
        </div>
      </div>

      {dictionaryScope && (
        <InfoMessage>
          В режиме «Все ЮЛ из справочника» показатели реестра считаются только для видимой
          страницы, поэтому сортировка и фильтры по количеству БС и вероятности недоступны.
        </InfoMessage>
      )}

      {error && <ErrorMessage message={error} onRetry={load} />}

      {loading ? (
        <TableSkeleton rows={10} columns={7} />
      ) : data.items.length === 0 ? (
        <EmptyState
          title="Ничего не найдено"
          description="Измените условия отбора или переключите режим списка"
        />
      ) : (
        <div className="card">
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <SortHeader
                    column="taxpayer_iin_bin"
                    label="БИН"
                    sort={sort}
                    order={order}
                    onSort={handleSort}
                  />
                  <SortHeader
                    column="taxpayer_name"
                    label="Наименование"
                    sort={sort}
                    order={order}
                    onSort={handleSort}
                  />
                  <SortHeader
                    column="code_nd"
                    label="Регион"
                    sort={sort}
                    order={order}
                    onSort={handleSort}
                  />
                  <th>Форма</th>
                  <th>Тип собственности</th>
                  {!dictionaryScope ? (
                    <>
                      <SortHeader
                        column="beneficiary_count"
                        label="БС"
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
                    </>
                  ) : (
                    <>
                      <th className="text-right">БС</th>
                      <th>Вероятность</th>
                    </>
                  )}
                  <SortHeader
                    column="reg_start_date"
                    label="Дата регистрации"
                    sort={sort}
                    order={order}
                    onSort={handleSort}
                  />
                </tr>
              </thead>
              <tbody>
                {data.items.map((item) => {
                  const style = riskStyle(item.max_ball3)
                  return (
                    <tr
                      key={item.taxpayer_iin_bin}
                      className="cursor-pointer"
                      onClick={() =>
                        navigate(`/company/${encodeURIComponent(item.taxpayer_iin_bin)}`)
                      }
                    >
                      <td className="whitespace-nowrap font-mono text-xs">
                        {value(item.taxpayer_iin_bin)}
                      </td>
                      <td>
                        <span className="font-medium text-slate-800">
                          {value(item.taxpayer_name)}
                        </span>
                        {item.is_state_owned && (
                          <span className="badge ml-2 bg-slate-200 text-slate-700">Гос</span>
                        )}
                      </td>
                      <td>{value(item.region || item.code_nd)}</td>
                      <td>{value(item.category)}</td>
                      <td className="max-w-[16rem] truncate" title={item.ownership_type}>
                        {value(item.ownership_type)}
                      </td>
                      <td className="text-right font-semibold">{number(item.beneficiary_count)}</td>
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
                      <td className="whitespace-nowrap">{value(item.reg_start_date)}</td>
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
    </div>
  )
}
