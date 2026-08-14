import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { errorMessage, registryApi } from '../api/client.js'
import {
  EmptyState,
  ErrorMessage,
  Loading,
  Spinner,
  riskStyle,
  value,
} from '../components/ui.jsx'

const ALGORITHM_OPTIONS = [
  'БС-1',
  'БС-2',
  'БС-3',
  'БС-4',
  'БС-6',
  'БС-7',
  'БС-8',
  'БС-9',
  'БС-10',
  'БС-11',
  'БС-13',
  'БС-16',
  'БС-17',
  'БС-22',
]

function StatTile({ label, count }) {
  return (
    <div className="card px-4 py-3">
      <div className="text-xs uppercase tracking-wide text-slate-500">{label}</div>
      <div className="mt-1 text-xl font-semibold text-slate-800">
        {count === null || count === undefined ? '—' : Number(count).toLocaleString('ru-RU')}
      </div>
    </div>
  )
}

function CompanyRow({ item, onOpen }) {
  const style = riskStyle(item.max_ball3)

  return (
    <button
      type="button"
      onClick={() => onOpen(item.taxpayer_iin_bin)}
      className="card w-full px-5 py-4 text-left transition-shadow hover:shadow-md"
    >
      <div className="flex flex-wrap items-start gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-semibold text-slate-800">
              {value(item.taxpayer_name)}
            </span>
            {item.is_state_owned && (
              <span className="badge bg-slate-200 text-slate-700">Гос</span>
            )}
          </div>
          <div className="mt-1 flex flex-wrap gap-x-5 gap-y-1 text-xs text-slate-500">
            <span>
              БИН: <span className="font-mono text-slate-700">{value(item.taxpayer_iin_bin)}</span>
            </span>
            <span>Регион: {value(item.region)}</span>
            <span>Форма: {value(item.category)}</span>
          </div>
        </div>

        <div className="flex items-center gap-6">
          <div className="text-center">
            <div className="text-[11px] uppercase tracking-wide text-slate-500">БС</div>
            <div className="text-lg font-semibold text-slate-800">{item.beneficiary_count}</div>
          </div>

          <div className="w-40">
            <div className="mb-1 flex items-center justify-between text-[11px]">
              <span className="text-slate-500">Вероятность</span>
              <span className={`font-semibold ${style.text}`}>
                {Number(item.max_ball3 || 0).toFixed(2)}%
              </span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-slate-200">
              <div
                className={`h-full rounded-full ${style.bar}`}
                style={{ width: `${Math.min(100, Number(item.max_ball3) || 0)}%` }}
              />
            </div>
          </div>
        </div>
      </div>
    </button>
  )
}

export default function SearchPage() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()

  const [query, setQuery] = useState(searchParams.get('query') || '')
  const [statusFilter, setStatusFilter] = useState(searchParams.get('status') || '')
  const [algorithm, setAlgorithm] = useState(searchParams.get('algorithm') || '')
  const [risk, setRisk] = useState(searchParams.get('risk') || '')

  const [results, setResults] = useState([])
  const [searched, setSearched] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const [stats, setStats] = useState(null)
  const [statsError, setStatsError] = useState('')

  useEffect(() => {
    registryApi
      .stats()
      .then(({ data }) => setStats(data))
      .catch((err) => setStatsError(errorMessage(err, 'Статистика недоступна')))
  }, [])

  const runSearch = useCallback(
    async (params) => {
      if (!params.query || params.query.trim().length < 2) {
        setError('Введите не менее двух символов для поиска')
        return
      }
      setLoading(true)
      setError('')
      try {
        const { data } = await registryApi.search({
          query: params.query.trim(),
          status: params.status || undefined,
          algorithm: params.algorithm || undefined,
          risk: params.risk || undefined,
          limit: 100,
        })
        setResults(data)
        setSearched(true)
      } catch (err) {
        setError(errorMessage(err, 'Поиск не выполнен'))
        setResults([])
      } finally {
        setLoading(false)
      }
    },
    [],
  )

  // Восстановление результатов при возврате со страницы карточки
  useEffect(() => {
    const initialQuery = searchParams.get('query')
    if (initialQuery && initialQuery.trim().length >= 2) {
      runSearch({
        query: initialQuery,
        status: searchParams.get('status') || '',
        algorithm: searchParams.get('algorithm') || '',
        risk: searchParams.get('risk') || '',
      })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleSubmit = (event) => {
    event.preventDefault()
    const params = { query, status: statusFilter, algorithm, risk }
    const next = {}
    Object.entries(params).forEach(([key, val]) => {
      if (val) next[key] = val
    })
    setSearchParams(next)
    runSearch(params)
  }

  const openCompany = (bin) => {
    navigate(`/company/${encodeURIComponent(bin)}?${searchParams.toString()}`)
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold text-slate-800">Поиск по реестру</h1>
        <p className="mt-0.5 text-sm text-slate-500">
          Поиск юридических лиц по БИН или наименованию с показателями бенефициарных собственников
        </p>
      </div>

      {stats && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <StatTile label="Компаний в реестре" count={stats.company_count} />
          <StatTile label="Бенефициаров" count={stats.beneficiary_count} />
          <StatTile label="Регистрационных" count={stats.registration_count} />
          <StatTile label="Предполагаемых" count={stats.assumed_count} />
          <StatTile label="Нерезидентов" count={stats.nonresident_count} />
          <StatTile
            label="Алгоритмов рассчитано"
            count={`${stats.algorithms_calculated} / ${stats.algorithms_total}`}
          />
        </div>
      )}
      {statsError && <ErrorMessage message={statsError} />}

      <form onSubmit={handleSubmit} className="card p-5">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-end">
          <div className="flex-1">
            <label className="label" htmlFor="query">
              БИН или наименование компании
            </label>
            <input
              id="query"
              className="input"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Например: 123456789012 или ТОО «Ромашка»"
            />
          </div>

          <div className="w-full lg:w-52">
            <label className="label" htmlFor="status">
              Тип БС
            </label>
            <select
              id="status"
              className="input"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
            >
              <option value="">Все компании</option>
              <option value="with_bs">С выявленными БС</option>
              <option value="without_bs">Без выявленных БС</option>
              <option value="state">Государственные</option>
            </select>
          </div>

          <div className="w-full lg:w-44">
            <label className="label" htmlFor="algorithm">
              Алгоритм
            </label>
            <select
              id="algorithm"
              className="input"
              value={algorithm}
              onChange={(e) => setAlgorithm(e.target.value)}
            >
              <option value="">Любой</option>
              {ALGORITHM_OPTIONS.map((code) => (
                <option key={code} value={code}>
                  {code}
                </option>
              ))}
            </select>
          </div>

          <div className="w-full lg:w-44">
            <label className="label" htmlFor="risk">
              Уровень риска
            </label>
            <select
              id="risk"
              className="input"
              value={risk}
              onChange={(e) => setRisk(e.target.value)}
            >
              <option value="">Любой</option>
              <option value="high">Высокий (свыше 70%)</option>
              <option value="medium">Средний (40–70%)</option>
              <option value="low">Низкий (до 40%)</option>
            </select>
          </div>

          <button type="submit" className="btn-primary lg:w-36" disabled={loading}>
            {loading && <Spinner className="h-4 w-4" />}
            {loading ? 'Поиск…' : 'Найти'}
          </button>
        </div>
      </form>

      {error && <ErrorMessage message={error} />}

      {loading && <Loading text="Идёт расчёт показателей реестра…" />}

      {!loading && searched && results.length === 0 && !error && (
        <EmptyState
          title="Ничего не найдено"
          description="Измените запрос или ослабьте фильтры"
        />
      )}

      {!loading && results.length > 0 && (
        <div className="space-y-2">
          <div className="text-sm text-slate-500">Найдено компаний: {results.length}</div>
          {results.map((item) => (
            <CompanyRow key={item.taxpayer_iin_bin} item={item} onOpen={openCompany} />
          ))}
        </div>
      )}
    </div>
  )
}
