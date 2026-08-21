import { useCallback, useEffect, useState } from 'react'
import { errorMessage, listingApi, algorithmsApi } from '../api/client.js'
import { useAuth } from '../context/AuthContext.jsx'
import Modal from '../components/Modal.jsx'
import {
  CardSkeleton,
  ErrorMessage,
  InfoMessage,
  PageHeader,
  Spinner,
  dateTime,
  number,
  value,
} from '../components/ui.jsx'

function TableRow({ table }) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-2 border-t border-slate-100 py-1.5 text-xs">
      <span className="font-mono text-slate-700">
        {table.name}
        {table.is_extra && (
          <span className="ml-2 font-sans text-[10px] text-slate-400">вспомогательная</span>
        )}
      </span>
      <span className="flex items-center gap-3">
        {table.exists ? (
          <>
            <span className="text-slate-600">
              {table.row_count == null ? '—' : `${number(table.row_count)} строк`}
            </span>
            <span className="text-slate-400">{table.modified_at || '—'}</span>
          </>
        ) : (
          <span className="text-amber-600">нет в ClickHouse</span>
        )}
      </span>
    </div>
  )
}

function SourceCard({ source }) {
  return (
    <div className="card p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-slate-800">{source.name}</h3>
          <p className="mt-0.5 text-xs text-slate-500">{source.organization}</p>
        </div>
        <div className="text-right">
          <div className="text-lg font-semibold text-slate-800">
            {source.row_count == null ? '—' : number(source.row_count)}
          </div>
          <div className="text-[11px] text-slate-400">записей</div>
        </div>
      </div>

      {source.note && <p className="mt-3 text-xs text-slate-600">{source.note}</p>}

      <div className="mt-3">
        <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
          Таблицы ClickHouse
        </div>
        {source.tables.length ? (
          source.tables.map((table) => <TableRow key={table.name} table={table} />)
        ) : (
          <div className="py-1.5 text-xs text-slate-400">не используются</div>
        )}
      </div>

      <div className="mt-3 border-t border-slate-100 pt-3">
        <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
          Алгоритмы
        </div>
        {source.algorithms.length ? (
          <div className="mt-1 flex flex-wrap gap-1">
            {source.algorithms.map((algorithm) => (
              <span
                key={algorithm.code}
                title={`${algorithm.name}${
                  algorithm.last_run_at ? ` · последний расчёт ${dateTime(algorithm.last_run_at)}` : ''
                }`}
                className={`badge font-mono ${
                  algorithm.last_run_status === 'success'
                    ? 'bg-emerald-100 text-emerald-800'
                    : algorithm.last_run_status === 'failed'
                      ? 'bg-red-100 text-red-800'
                      : 'bg-slate-100 text-slate-700'
                }`}
              >
                {algorithm.code}
              </span>
            ))}
          </div>
        ) : (
          <div className="mt-1 text-xs text-slate-400">алгоритм в ТЗ не описан</div>
        )}
      </div>

      {source.updated_at && (
        <div className="mt-3 text-[11px] text-slate-400">
          Обновление структуры: {source.updated_at}
        </div>
      )}
    </div>
  )
}

/** Таблица алгоритмов для администратора: просмотр SQL и запуск. */
function AlgorithmsPanel() {
  const [algorithms, setAlgorithms] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [viewing, setViewing] = useState(null)
  const [running, setRunning] = useState('')
  const [runResult, setRunResult] = useState('')

  const load = useCallback(() => {
    setLoading(true)
    algorithmsApi
      .list()
      .then(({ data }) => setAlgorithms(data))
      .catch((err) => setError(errorMessage(err, 'Список алгоритмов не загружен')))
      .finally(() => setLoading(false))
  }, [])

  useEffect(load, [load])

  const runAlgorithm = async (code) => {
    setRunning(code)
    setRunResult('')
    setError('')
    try {
      const { data } = await algorithmsApi.run(code)
      setRunResult(
        `${code}: выполнен за ${(data.duration_ms / 1000).toFixed(1)} с, строк ${number(data.row_count)}`,
      )
      load()
    } catch (err) {
      setError(errorMessage(err, `Алгоритм ${code} не выполнен`))
    } finally {
      setRunning('')
    }
  }

  return (
    <div className="card">
      <div className="card-header">
        <span className="card-title">Алгоритмы, использующие источники</span>
        <button type="button" className="btn-secondary" onClick={load} disabled={loading}>
          Обновить
        </button>
      </div>

      {error && (
        <div className="px-5 pt-4">
          <ErrorMessage message={error} />
        </div>
      )}
      {runResult && (
        <div className="px-5 pt-4">
          <InfoMessage tone="success">{runResult}</InfoMessage>
        </div>
      )}

      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>Код</th>
              <th>Название</th>
              <th>Источник</th>
              <th>Таблица результата</th>
              <th className="text-right">Балл</th>
              <th className="text-right">Строк</th>
              <th>Последний расчёт</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {algorithms.map((algorithm) => (
              <tr key={algorithm.code}>
                <td className="whitespace-nowrap font-mono text-xs font-semibold">
                  {algorithm.code}
                </td>
                <td>{value(algorithm.name)}</td>
                <td className="text-xs">{value(algorithm.source)}</td>
                <td className="font-mono text-xs">{value(algorithm.clickhouse_result_table)}</td>
                <td className="text-right">{algorithm.priority_score}</td>
                <td className="text-right">{number(algorithm.last_row_count)}</td>
                <td className="whitespace-nowrap text-xs">
                  <span
                    className={
                      algorithm.last_run_status === 'failed' ? 'text-red-600' : 'text-slate-600'
                    }
                  >
                    {algorithm.last_run_at ? dateTime(algorithm.last_run_at) : '—'}
                  </span>
                </td>
                <td className="whitespace-nowrap text-right">
                  <button
                    type="button"
                    className="mr-2 text-sm text-afm-600 hover:underline"
                    onClick={() => setViewing(algorithm)}
                  >
                    SQL
                  </button>
                  <button
                    type="button"
                    className="text-sm text-afm-600 hover:underline disabled:opacity-40"
                    onClick={() => runAlgorithm(algorithm.code)}
                    disabled={Boolean(running)}
                  >
                    {running === algorithm.code ? 'Расчёт…' : 'Запустить'}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Modal
        open={Boolean(viewing)}
        onClose={() => setViewing(null)}
        title={viewing ? `${viewing.code} — ${viewing.name}` : ''}
        size="xl"
      >
        {viewing && (
          <>
            <p className="mb-3 text-sm text-slate-600">{viewing.description}</p>
            <pre className="max-h-[60vh] overflow-auto rounded-md bg-slate-900 p-4 text-xs leading-relaxed text-slate-100">
              {viewing.sql_script}
            </pre>
          </>
        )}
      </Modal>
    </div>
  )
}

export default function SourcesPage() {
  const { isAdministrator } = useAuth()
  const [sources, setSources] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(() => {
    setLoading(true)
    setError('')
    listingApi
      .sources()
      .then(({ data }) => setSources(data))
      .catch((err) => setError(errorMessage(err, 'Каталог источников не загружен')))
      .finally(() => setLoading(false))
  }, [])

  useEffect(load, [load])

  return (
    <div className="space-y-4">
      <PageHeader
        title="Источники данных"
        description="Ведомственные массивы, на которых строится реестр бенефициарных собственников"
      >
        <button type="button" className="btn-secondary" onClick={load} disabled={loading}>
          {loading && <Spinner className="h-4 w-4" />}
          Обновить
        </button>
      </PageHeader>

      {error && <ErrorMessage message={error} onRetry={load} />}

      {loading ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, index) => (
            <CardSkeleton key={index} lines={5} />
          ))}
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {sources.map((source) => (
            <SourceCard key={source.key} source={source} />
          ))}
        </div>
      )}

      {isAdministrator && <AlgorithmsPanel />}
    </div>
  )
}
