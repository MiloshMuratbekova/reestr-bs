import { useCallback, useEffect, useState } from 'react'
import { errorMessage, scheduleApi } from '../api/client.js'
import Modal from '../components/Modal.jsx'
import {
  EmptyState,
  ErrorMessage,
  InfoMessage,
  PageHeader,
  Spinner,
  TableSkeleton,
  dateTime,
  number,
  value,
} from '../components/ui.jsx'

const STATUS_LABELS = {
  running: { text: 'Выполняется', className: 'bg-afm-100 text-afm-800' },
  success: { text: 'Успешно', className: 'bg-emerald-100 text-emerald-800' },
  partial: { text: 'Частично', className: 'bg-amber-100 text-amber-800' },
  failed: { text: 'Ошибка', className: 'bg-red-100 text-red-800' },
}

const TRIGGER_LABELS = { schedule: 'по расписанию', manual: 'вручную' }

function duration(ms) {
  const seconds = Math.round((Number(ms) || 0) / 1000)
  if (seconds < 60) return `${seconds} с`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes} мин ${seconds % 60} с`
  return `${Math.floor(minutes / 60)} ч ${minutes % 60} мин`
}

export default function SchedulePage() {
  const [schedule, setSchedule] = useState(null)
  const [runs, setRuns] = useState([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [details, setDetails] = useState(null)

  const [enabled, setEnabled] = useState(false)
  const [runTime, setRunTime] = useState('03:00')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [{ data: current }, { data: history }] = await Promise.all([
        scheduleApi.get(),
        scheduleApi.runs(20),
      ])
      setSchedule(current)
      setEnabled(current.enabled)
      setRunTime(current.run_time || '03:00')
      setRuns(history)
    } catch (err) {
      setError(errorMessage(err, 'Расписание не загружено'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const save = async () => {
    setSaving(true)
    setError('')
    setNotice('')
    try {
      const { data } = await scheduleApi.save({ enabled, run_time: runTime })
      setSchedule(data)
      setNotice(
        data.enabled
          ? `Расписание сохранено. Следующий пересчёт: ${dateTime(data.next_run_at)}`
          : 'Расписание сохранено, автоматический пересчёт выключен',
      )
    } catch (err) {
      setError(errorMessage(err, 'Расписание не сохранено'))
    } finally {
      setSaving(false)
    }
  }

  const runNow = async () => {
    setRunning(true)
    setError('')
    setNotice('')
    try {
      const { data } = await scheduleApi.runNow()
      setNotice(
        `Пересчёт завершён: успешно ${number(data.succeeded)} из ${number(data.total)}, ` +
          `строк ${number(data.total_rows)}, время ${duration(data.duration_ms)}`,
      )
      await load()
    } catch (err) {
      setError(errorMessage(err, 'Пересчёт не выполнен'))
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="Расписание пересчёта"
        description="Ночной прогон всех алгоритмов выявления БС и история запусков"
      />

      {error && <ErrorMessage message={error} />}
      {notice && <InfoMessage tone="success">{notice}</InfoMessage>}

      <div className="card p-5">
        <div className="grid gap-4 md:grid-cols-3">
          <div>
            <label className="label" htmlFor="run-time">
              Время запуска ({schedule?.timezone || 'Asia/Almaty'})
            </label>
            <input
              id="run-time"
              type="time"
              className="input"
              value={runTime}
              onChange={(event) => setRunTime(event.target.value)}
            />
          </div>

          <div className="flex items-end">
            <label className="flex items-center gap-2 pb-2 text-sm text-slate-700">
              <input
                type="checkbox"
                checked={enabled}
                onChange={(event) => setEnabled(event.target.checked)}
              />
              Пересчитывать автоматически
            </label>
          </div>

          <div className="flex items-end justify-end gap-2">
            <button type="button" className="btn-primary" onClick={save} disabled={saving}>
              {saving && <Spinner className="h-4 w-4" />}
              Сохранить
            </button>
            <button
              type="button"
              className="btn-secondary"
              onClick={runNow}
              disabled={running}
            >
              {running && <Spinner className="h-4 w-4" />}
              {running ? 'Пересчёт идёт…' : 'Запустить сейчас'}
            </button>
          </div>
        </div>

        <div className="mt-4 grid gap-3 border-t border-slate-100 pt-4 text-sm sm:grid-cols-3">
          <div>
            <div className="text-xs uppercase tracking-wide text-slate-500">Следующий запуск</div>
            <div className="mt-0.5 text-slate-800">
              {schedule?.enabled ? dateTime(schedule?.next_run_at) : 'не запланирован'}
            </div>
          </div>
          <div>
            <div className="text-xs uppercase tracking-wide text-slate-500">Последний запуск</div>
            <div className="mt-0.5 text-slate-800">{dateTime(schedule?.last_run_at)}</div>
          </div>
          <div>
            <div className="text-xs uppercase tracking-wide text-slate-500">Изменил</div>
            <div className="mt-0.5 text-slate-800">{value(schedule?.updated_by)}</div>
          </div>
        </div>

        <InfoMessage>
          Пересчёт идёт последовательно и с учётом зависимостей: БС-11 и БС-13 считаются после
          БС-1 и БС-3, БС-17 — после БС-1, БС-2, БС-22, БС-3 и БС-4. Если алгоритм упал,
          зависящие от него пропускаются, остальные считаются дальше. Запуск вручную во время
          уже идущего пересчёта отклоняется.
        </InfoMessage>
      </div>

      <div className="card">
        <div className="card-header">
          <span className="card-title">История запусков</span>
          <button type="button" className="btn-secondary" onClick={load} disabled={loading}>
            Обновить
          </button>
        </div>

        {loading ? (
          <TableSkeleton rows={5} columns={7} />
        ) : runs.length === 0 ? (
          <EmptyState
            title="Пересчётов ещё не было"
            description="Запустите вручную или включите расписание"
          />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Начало</th>
                  <th>Тип</th>
                  <th>Состояние</th>
                  <th className="text-right">Успешно</th>
                  <th className="text-right">Ошибок</th>
                  <th className="text-right">Строк</th>
                  <th className="text-right">Время</th>
                  <th>Инициатор</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => {
                  const status = STATUS_LABELS[run.status] || STATUS_LABELS.running
                  return (
                    <tr key={run.id}>
                      <td className="whitespace-nowrap text-xs">{dateTime(run.started_at)}</td>
                      <td className="text-xs">{TRIGGER_LABELS[run.trigger] || run.trigger}</td>
                      <td>
                        <span className={`badge ${status.className}`}>{status.text}</span>
                      </td>
                      <td className="text-right">{number(run.succeeded)}</td>
                      <td className="text-right">
                        <span className={run.failed > 0 ? 'font-semibold text-red-600' : ''}>
                          {number(run.failed)}
                        </span>
                      </td>
                      <td className="text-right">{number(run.total_rows)}</td>
                      <td className="whitespace-nowrap text-right text-xs">
                        {duration(run.duration_ms)}
                      </td>
                      <td className="text-xs">{value(run.triggered_by)}</td>
                      <td className="text-right">
                        <button
                          type="button"
                          className="text-sm text-afm-600 hover:underline"
                          onClick={() => setDetails(run)}
                        >
                          Подробно
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <Modal
        open={Boolean(details)}
        onClose={() => setDetails(null)}
        title={details ? `Пересчёт от ${dateTime(details.started_at)}` : ''}
        size="xl"
      >
        {details && (
          <>
            {details.error && <ErrorMessage message={details.error} />}
            <table className="table mt-3">
              <thead>
                <tr>
                  <th>Алгоритм</th>
                  <th>Состояние</th>
                  <th className="text-right">Строк</th>
                  <th className="text-right">Время</th>
                  <th>Ошибка</th>
                </tr>
              </thead>
              <tbody>
                {(details.details || []).map((item) => (
                  <tr key={item.code}>
                    <td className="font-mono text-xs font-semibold">{item.code}</td>
                    <td>
                      <span
                        className={`badge ${
                          item.status === 'success'
                            ? 'bg-emerald-100 text-emerald-800'
                            : item.status === 'skipped'
                              ? 'bg-amber-100 text-amber-800'
                              : 'bg-red-100 text-red-800'
                        }`}
                      >
                        {item.status === 'success'
                          ? 'успешно'
                          : item.status === 'skipped'
                            ? 'пропущен'
                            : 'ошибка'}
                      </span>
                    </td>
                    <td className="text-right">{number(item.row_count)}</td>
                    <td className="text-right text-xs">
                      {item.duration_ms ? duration(item.duration_ms) : '—'}
                    </td>
                    <td className="max-w-[28rem] text-xs text-red-700">{item.error || ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </Modal>
    </div>
  )
}
