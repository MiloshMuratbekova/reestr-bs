import { useCallback, useEffect, useState } from 'react'
import { errorMessage, reportsApi, saveBlob } from '../api/client.js'
import { useAuth } from '../context/AuthContext.jsx'
import {
  CardSkeleton,
  EmptyState,
  ErrorMessage,
  InfoMessage,
  PageHeader,
  Spinner,
  TableSkeleton,
  dateTime,
  fileSize,
  number,
  value,
} from '../components/ui.jsx'

const FORMAT_LABELS = { xlsx: 'Excel', pdf: 'PDF' }

function TemplateCard({ template, onGenerate, busy }) {
  const [limit, setLimit] = useState(5000)
  const [threshold, setThreshold] = useState(70)

  const hasLimit = template.parameters.includes('limit')
  const hasThreshold = template.parameters.includes('threshold')

  const parameters = () => {
    const payload = {}
    if (hasLimit) payload.limit = Number(limit) || 5000
    if (hasThreshold) payload.threshold = Number(threshold) || 70
    return payload
  }

  return (
    <div className="card flex flex-col p-5">
      <h3 className="text-sm font-semibold text-slate-800">{template.title}</h3>
      <p className="mt-1 flex-1 text-xs text-slate-600">{template.description}</p>

      {(hasLimit || hasThreshold) && (
        <div className="mt-3 grid grid-cols-2 gap-3">
          {hasLimit && (
            <div>
              <label className="label" htmlFor={`limit-${template.key}`}>
                Строк, не более
              </label>
              <input
                id={`limit-${template.key}`}
                type="number"
                className="input"
                min={1}
                max={100000}
                value={limit}
                onChange={(event) => setLimit(event.target.value)}
              />
            </div>
          )}
          {hasThreshold && (
            <div>
              <label className="label" htmlFor={`threshold-${template.key}`}>
                Порог вероятности, %
              </label>
              <input
                id={`threshold-${template.key}`}
                type="number"
                className="input"
                min={0}
                max={100}
                value={threshold}
                onChange={(event) => setThreshold(event.target.value)}
              />
            </div>
          )}
        </div>
      )}

      <div className="mt-4 flex gap-2">
        <button
          type="button"
          className="btn-primary flex-1"
          disabled={busy}
          onClick={() => onGenerate(template, 'xlsx', parameters())}
        >
          {busy === `${template.key}:xlsx` && <Spinner className="h-4 w-4" />}
          Excel
        </button>
        <button
          type="button"
          className="btn-secondary flex-1"
          disabled={busy}
          onClick={() => onGenerate(template, 'pdf', parameters())}
        >
          {busy === `${template.key}:pdf` && <Spinner className="h-4 w-4" />}
          PDF
        </button>
      </div>

      <div className="mt-2 text-[11px] text-slate-400">
        Столбцов в выгрузке: {template.columns.length}
      </div>
    </div>
  )
}

export default function ReportsPage() {
  const { isAdministrator } = useAuth()

  const [templates, setTemplates] = useState([])
  const [history, setHistory] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState('')
  const [downloading, setDownloading] = useState(0)

  const loadHistory = useCallback(async () => {
    const { data } = await reportsApi.history(30)
    setHistory(data)
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [{ data: templateList }] = await Promise.all([reportsApi.templates()])
      setTemplates(templateList)
      await loadHistory()
    } catch (err) {
      setError(errorMessage(err, 'Не удалось загрузить отчёты'))
    } finally {
      setLoading(false)
    }
  }, [loadHistory])

  useEffect(() => {
    load()
  }, [load])

  const generate = async (template, fileFormat, parameters) => {
    setBusy(`${template.key}:${fileFormat}`)
    setError('')
    setNotice('')
    try {
      const { data: report } = await reportsApi.generate(template.key, fileFormat, parameters)
      setNotice(
        `«${report.title}» сформирован: строк ${number(report.row_count)}, ` +
          `${fileSize(report.file_size)}, ${(report.duration_ms / 1000).toFixed(1)} с`,
      )
      await loadHistory()
    } catch (err) {
      setError(errorMessage(err, 'Отчёт не сформирован'))
    } finally {
      setBusy('')
    }
  }

  const download = async (report) => {
    setDownloading(report.id)
    setError('')
    try {
      const { data: blob } = await reportsApi.download(report.id)
      saveBlob(blob, report.file_name)
    } catch (err) {
      setError(errorMessage(err, 'Файл отчёта не получен'))
    } finally {
      setDownloading(0)
    }
  }

  const remove = async (report) => {
    setError('')
    try {
      await reportsApi.remove(report.id)
      await loadHistory()
    } catch (err) {
      setError(errorMessage(err, 'Отчёт не удалён'))
    }
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="Отчёты"
        description="Выгрузки реестра в Excel и PDF. Файлы хранятся на сервере и доступны повторно"
      />

      {error && <ErrorMessage message={error} />}
      {notice && <InfoMessage tone="success">{notice}</InfoMessage>}

      {loading ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <CardSkeleton key={index} lines={4} />
          ))}
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {templates.map((template) => (
            <TemplateCard
              key={template.key}
              template={template}
              onGenerate={generate}
              busy={busy}
            />
          ))}
        </div>
      )}

      <div className="card">
        <div className="card-header">
          <span className="card-title">История сформированных отчётов</span>
          <button
            type="button"
            className="btn-secondary"
            onClick={loadHistory}
            disabled={loading}
          >
            Обновить
          </button>
        </div>

        {loading ? (
          <TableSkeleton rows={5} columns={6} />
        ) : history.length === 0 ? (
          <EmptyState
            title="Отчёты ещё не формировались"
            description="Выберите шаблон выше и нажмите Excel или PDF"
          />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Отчёт</th>
                  <th>Формат</th>
                  <th className="text-right">Строк</th>
                  <th className="text-right">Размер</th>
                  <th>Сформирован</th>
                  <th>Кем</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {history.map((report) => (
                  <tr key={report.id}>
                    <td>
                      <div className="font-medium text-slate-800">{value(report.title)}</div>
                      <div className="font-mono text-[11px] text-slate-400">
                        {report.file_name}
                      </div>
                    </td>
                    <td>
                      <span className="badge bg-slate-100 text-slate-700">
                        {FORMAT_LABELS[report.file_format] || report.file_format}
                      </span>
                    </td>
                    <td className="text-right">{number(report.row_count)}</td>
                    <td className="text-right">{fileSize(report.file_size)}</td>
                    <td className="whitespace-nowrap text-xs">{dateTime(report.created_at)}</td>
                    <td className="text-xs">{value(report.created_by)}</td>
                    <td className="whitespace-nowrap text-right">
                      <button
                        type="button"
                        className="mr-3 text-sm text-afm-600 hover:underline disabled:opacity-40"
                        onClick={() => download(report)}
                        disabled={downloading === report.id}
                      >
                        {downloading === report.id ? 'Загрузка…' : 'Скачать'}
                      </button>
                      {isAdministrator && (
                        <button
                          type="button"
                          className="text-sm text-red-600 hover:underline"
                          onClick={() => remove(report)}
                        >
                          Удалить
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
