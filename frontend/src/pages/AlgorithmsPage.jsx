import { useCallback, useEffect, useState } from 'react'
import { algorithmsApi, errorMessage } from '../api/client.js'
import Modal from '../components/Modal.jsx'
import {
  EmptyState,
  ErrorMessage,
  InfoMessage,
  Loading,
  Spinner,
  value,
} from '../components/ui.jsx'
import { diffLines, diffSummary } from '../utils/diff.js'

const EMPTY_FORM = {
  code: '',
  name: '',
  description: '',
  sql_script: '',
  clickhouse_result_table: '',
  source: '',
  priority_score: 0,
  is_active: true,
  depends_on: '',
  order_index: 100,
}

/* -------------------------------------------------------------------------- */
function RunStatus({ algorithm }) {
  if (!algorithm.last_run_status) {
    return <span className="text-xs text-slate-400">не запускался</span>
  }
  if (algorithm.last_run_status === 'success') {
    return (
      <div className="text-xs">
        <span className="badge bg-emerald-100 text-emerald-800">успешно</span>
        <div className="mt-0.5 text-slate-500">
          строк: {Number(algorithm.last_row_count ?? 0).toLocaleString('ru-RU')}
        </div>
      </div>
    )
  }
  return (
    <div className="text-xs">
      <span className="badge bg-red-100 text-red-800">ошибка</span>
      {algorithm.last_error && (
        <div className="mt-0.5 max-w-xs truncate text-slate-500" title={algorithm.last_error}>
          {algorithm.last_error}
        </div>
      )}
    </div>
  )
}

/* -------------------------------------------------------------------------- */
function DiffView({ oldSql, newSql }) {
  const rows = diffLines(oldSql, newSql)
  const summary = diffSummary(rows)

  return (
    <div>
      <div className="mb-2 flex gap-4 text-xs">
        <span className="text-emerald-700">Добавлено строк: {summary.added}</span>
        <span className="text-red-700">Удалено строк: {summary.removed}</span>
      </div>

      <div className="overflow-x-auto rounded border border-slate-200 bg-slate-50">
        <pre className="min-w-full text-xs leading-relaxed">
          {rows.map((row, index) => {
            const tone =
              row.type === 'added'
                ? 'bg-emerald-50 text-emerald-900'
                : row.type === 'removed'
                  ? 'bg-red-50 text-red-900'
                  : 'text-slate-600'
            const sign = row.type === 'added' ? '+' : row.type === 'removed' ? '−' : ' '
            return (
              <div key={index} className={`flex ${tone}`}>
                <span className="w-10 shrink-0 select-none border-r border-slate-200 px-1 text-right text-slate-400">
                  {row.oldNo ?? ''}
                </span>
                <span className="w-10 shrink-0 select-none border-r border-slate-200 px-1 text-right text-slate-400">
                  {row.newNo ?? ''}
                </span>
                <span className="w-5 shrink-0 select-none text-center">{sign}</span>
                <span className="whitespace-pre px-2 font-mono">{row.text || ' '}</span>
              </div>
            )
          })}
        </pre>
      </div>
    </div>
  )
}

/* -------------------------------------------------------------------------- */
export default function AlgorithmsPage() {
  const [algorithms, setAlgorithms] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState('') // код алгоритма, по которому идёт операция

  const [viewing, setViewing] = useState(null)
  const [editing, setEditing] = useState(null)
  const [editSql, setEditSql] = useState('')
  const [editReason, setEditReason] = useState('')
  const [creating, setCreating] = useState(false)
  const [form, setForm] = useState(EMPTY_FORM)

  const [aiTarget, setAiTarget] = useState(null)
  const [aiRequirement, setAiRequirement] = useState('')
  const [aiResult, setAiResult] = useState(null)
  const [aiLoading, setAiLoading] = useState(false)
  const [aiError, setAiError] = useState('')

  const [recalcResult, setRecalcResult] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const { data } = await algorithmsApi.list()
      setAlgorithms(data)
    } catch (err) {
      setError(errorMessage(err, 'Не удалось загрузить список алгоритмов'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  /* --- запуск одного алгоритма --- */
  const runAlgorithm = async (code) => {
    setBusy(code)
    setError('')
    setNotice('')
    try {
      const { data } = await algorithmsApi.run(code)
      setNotice(
        `Алгоритм ${code} выполнен за ${(data.duration_ms / 1000).toFixed(1)} с. ` +
          `Строк в результате: ${Number(data.row_count ?? 0).toLocaleString('ru-RU')}.`,
      )
      await load()
    } catch (err) {
      setError(errorMessage(err, `Не удалось выполнить алгоритм ${code}`))
    } finally {
      setBusy('')
    }
  }

  /* --- полный пересчёт --- */
  const recalculate = async () => {
    if (!window.confirm('Запустить пересчёт всех активных алгоритмов? Операция может занять часы.')) {
      return
    }
    setBusy('__recalc__')
    setError('')
    setNotice('')
    setRecalcResult(null)
    try {
      const { data } = await algorithmsApi.recalculate()
      setRecalcResult(data)
      setNotice(
        `Пересчёт завершён за ${(data.duration_ms / 1000 / 60).toFixed(1)} мин. ` +
          `Успешно: ${data.succeeded}, с ошибками: ${data.failed}.`,
      )
      await load()
    } catch (err) {
      setError(errorMessage(err, 'Пересчёт не выполнен'))
    } finally {
      setBusy('')
    }
  }

  /* --- сохранение правки SQL --- */
  const saveEdit = async () => {
    setBusy(editing.code)
    setError('')
    setNotice('')
    try {
      const { data } = await algorithmsApi.update(editing.code, {
        sql_script: editSql,
        reason: editReason || 'Изменение через интерфейс',
        execute: true,
      })
      if (data.run_error) {
        setError(
          `SQL сохранён (версия ${data.algorithm.version}), но выполнение в ClickHouse ` +
            `завершилось ошибкой: ${data.run_error}`,
        )
      } else {
        const rows = data.run?.row_count
        setNotice(
          `Алгоритм ${editing.code} обновлён до версии ${data.algorithm.version}` +
            (rows != null ? `, строк в результате: ${Number(rows).toLocaleString('ru-RU')}` : ''),
        )
      }
      setEditing(null)
      await load()
    } catch (err) {
      setError(errorMessage(err, 'Не удалось сохранить изменения'))
    } finally {
      setBusy('')
    }
  }

  /* --- создание алгоритма --- */
  const createAlgorithm = async () => {
    setBusy('__create__')
    setError('')
    try {
      await algorithmsApi.create({
        ...form,
        priority_score: Number(form.priority_score) || 0,
        order_index: Number(form.order_index) || 100,
        depends_on: form.depends_on
          ? form.depends_on.split(',').map((s) => s.trim()).filter(Boolean)
          : [],
      })
      setNotice(`Алгоритм ${form.code} создан`)
      setCreating(false)
      setForm(EMPTY_FORM)
      await load()
    } catch (err) {
      setError(errorMessage(err, 'Не удалось создать алгоритм'))
    } finally {
      setBusy('')
    }
  }

  /* --- запрос предложения у ИИ --- */
  const requestAiUpdate = async () => {
    if (aiRequirement.trim().length < 5) {
      setAiError('Опишите новое бизнес-требование подробнее')
      return
    }
    setAiLoading(true)
    setAiError('')
    setAiResult(null)
    try {
      const { data } = await algorithmsApi.aiUpdate(aiTarget.code, aiRequirement.trim())
      setAiResult(data)
    } catch (err) {
      setAiError(errorMessage(err, 'Модель не смогла подготовить новый SQL'))
    } finally {
      setAiLoading(false)
    }
  }

  /* --- одобрение предложения ИИ --- */
  const approveAiUpdate = async () => {
    setBusy(aiTarget.code)
    setError('')
    try {
      const { data } = await algorithmsApi.update(aiTarget.code, {
        sql_script: aiResult.new_sql,
        reason: `Обновление по требованию через ИИ: ${aiRequirement.trim()}`,
        execute: true,
      })
      if (data.run_error) {
        setError(
          `SQL сохранён (версия ${data.algorithm.version}), но выполнение в ClickHouse ` +
            `завершилось ошибкой: ${data.run_error}`,
        )
      } else {
        setNotice(`Алгоритм ${aiTarget.code} обновлён до версии ${data.algorithm.version}`)
      }
      closeAi()
      await load()
    } catch (err) {
      setError(errorMessage(err, 'Не удалось применить предложение'))
    } finally {
      setBusy('')
    }
  }

  const closeAi = () => {
    setAiTarget(null)
    setAiRequirement('')
    setAiResult(null)
    setAiError('')
  }

  /* ------------------------------------------------------------------------ */
  if (loading) return <Loading text="Загрузка алгоритмов…" />

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-slate-800">Управление алгоритмами</h1>
          <p className="mt-0.5 text-sm text-slate-500">
            SQL алгоритмов хранится в PostgreSQL и выполняется в ClickHouse
          </p>
        </div>
        <div className="flex gap-2">
          <button type="button" className="btn-secondary" onClick={() => setCreating(true)}>
            Добавить алгоритм
          </button>
          <button
            type="button"
            className="btn-primary"
            onClick={recalculate}
            disabled={busy === '__recalc__'}
          >
            {busy === '__recalc__' && <Spinner className="h-4 w-4" />}
            {busy === '__recalc__' ? 'Идёт пересчёт…' : 'Пересчитать всё'}
          </button>
        </div>
      </div>

      {notice && <InfoMessage tone="success">{notice}</InfoMessage>}
      {error && <ErrorMessage message={error} />}

      {recalcResult && (
        <section className="card">
          <div className="card-header">
            <h2 className="card-title">Результат пересчёта</h2>
          </div>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Алгоритм</th>
                  <th>Статус</th>
                  <th>Строк</th>
                  <th>Время</th>
                  <th>Сообщение</th>
                </tr>
              </thead>
              <tbody>
                {recalcResult.results.map((row) => (
                  <tr key={row.code}>
                    <td className="font-mono">{row.code}</td>
                    <td>
                      <span
                        className={`badge ${
                          row.status === 'success'
                            ? 'bg-emerald-100 text-emerald-800'
                            : row.status === 'skipped'
                              ? 'bg-slate-100 text-slate-700'
                              : 'bg-red-100 text-red-800'
                        }`}
                      >
                        {row.status === 'success'
                          ? 'успешно'
                          : row.status === 'skipped'
                            ? 'пропущен'
                            : 'ошибка'}
                      </span>
                    </td>
                    <td>
                      {row.row_count != null
                        ? Number(row.row_count).toLocaleString('ru-RU')
                        : '—'}
                    </td>
                    <td>
                      {row.duration_ms != null ? `${(row.duration_ms / 1000).toFixed(1)} с` : '—'}
                    </td>
                    <td className="max-w-md text-xs text-slate-500">{row.error || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <section className="card">
        {algorithms.length === 0 ? (
          <EmptyState title="Алгоритмы не заданы" />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Код</th>
                  <th>Название</th>
                  <th>Источник</th>
                  <th>Балл</th>
                  <th>Таблица результата</th>
                  <th>Верс.</th>
                  <th>Последний запуск</th>
                  <th>Активен</th>
                  <th className="text-right">Действия</th>
                </tr>
              </thead>
              <tbody>
                {algorithms.map((algorithm) => (
                  <tr key={algorithm.code}>
                    <td className="font-mono font-semibold">{algorithm.code}</td>
                    <td>
                      <div className="text-sm text-slate-800">{algorithm.name}</div>
                      {algorithm.depends_on && (
                        <div className="text-xs text-slate-400">
                          зависит от: {algorithm.depends_on}
                        </div>
                      )}
                    </td>
                    <td className="text-xs">{value(algorithm.source)}</td>
                    <td>{algorithm.priority_score}</td>
                    <td className="font-mono text-xs">
                      {value(algorithm.clickhouse_result_table)}
                    </td>
                    <td>{algorithm.version}</td>
                    <td>
                      <RunStatus algorithm={algorithm} />
                    </td>
                    <td>
                      <span
                        className={`badge ${
                          algorithm.is_active
                            ? 'bg-emerald-100 text-emerald-800'
                            : 'bg-slate-100 text-slate-600'
                        }`}
                      >
                        {algorithm.is_active ? 'да' : 'нет'}
                      </span>
                    </td>
                    <td>
                      <div className="flex justify-end gap-1">
                        <button
                          type="button"
                          className="btn-secondary px-2 py-1 text-xs"
                          onClick={() => setViewing(algorithm)}
                        >
                          SQL
                        </button>
                        <button
                          type="button"
                          className="btn-secondary px-2 py-1 text-xs"
                          onClick={() => {
                            setEditing(algorithm)
                            setEditSql(algorithm.sql_script)
                            setEditReason('')
                          }}
                        >
                          Изменить
                        </button>
                        <button
                          type="button"
                          className="btn-secondary px-2 py-1 text-xs"
                          onClick={() => runAlgorithm(algorithm.code)}
                          disabled={busy === algorithm.code}
                        >
                          {busy === algorithm.code ? <Spinner className="h-3 w-3" /> : 'Запуск'}
                        </button>
                        <button
                          type="button"
                          className="btn-secondary px-2 py-1 text-xs"
                          onClick={() => {
                            setAiTarget(algorithm)
                            setAiRequirement('')
                            setAiResult(null)
                            setAiError('')
                          }}
                        >
                          ИИ
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* --- просмотр SQL --- */}
      <Modal
        open={Boolean(viewing)}
        title={viewing ? `${viewing.code} — ${viewing.name}` : ''}
        onClose={() => setViewing(null)}
        size="xl"
        footer={
          <button type="button" className="btn-secondary" onClick={() => setViewing(null)}>
            Закрыть
          </button>
        }
      >
        {viewing && (
          <div className="space-y-4">
            <div>
              <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
                Описание логики
              </h3>
              <p className="text-sm leading-relaxed text-slate-700">{viewing.description}</p>
            </div>
            <div>
              <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
                SQL код
              </h3>
              <pre className="overflow-x-auto rounded border border-slate-200 bg-slate-50 p-3 font-mono text-xs leading-relaxed text-slate-700">
                {viewing.sql_script}
              </pre>
            </div>
          </div>
        )}
      </Modal>

      {/* --- редактирование SQL --- */}
      <Modal
        open={Boolean(editing)}
        title={editing ? `Изменение SQL: ${editing.code}` : ''}
        onClose={() => setEditing(null)}
        size="xl"
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={() => setEditing(null)}>
              Отмена
            </button>
            <button
              type="button"
              className="btn-primary"
              onClick={saveEdit}
              disabled={busy === editing?.code}
            >
              {busy === editing?.code && <Spinner className="h-4 w-4" />}
              Сохранить и выполнить
            </button>
          </>
        }
      >
        {editing && (
          <div className="space-y-3">
            <InfoMessage>
              Прежняя версия SQL сохранится в истории изменений. После сохранения алгоритм будет
              выполнен в ClickHouse.
            </InfoMessage>
            <div>
              <label className="label" htmlFor="reason">
                Причина изменения
              </label>
              <input
                id="reason"
                className="input"
                value={editReason}
                onChange={(e) => setEditReason(e.target.value)}
                placeholder="Например: уточнён порог суммы операций"
              />
            </div>
            <div>
              <label className="label" htmlFor="sql">
                SQL код
              </label>
              <textarea
                id="sql"
                className="input h-96 font-mono text-xs"
                value={editSql}
                onChange={(e) => setEditSql(e.target.value)}
                spellCheck={false}
              />
            </div>
          </div>
        )}
      </Modal>

      {/* --- создание алгоритма --- */}
      <Modal
        open={creating}
        title="Новый алгоритм"
        onClose={() => setCreating(false)}
        size="xl"
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={() => setCreating(false)}>
              Отмена
            </button>
            <button
              type="button"
              className="btn-primary"
              onClick={createAlgorithm}
              disabled={busy === '__create__' || !form.code || !form.name || !form.sql_script}
            >
              {busy === '__create__' && <Spinner className="h-4 w-4" />}
              Создать
            </button>
          </>
        }
      >
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <div>
            <label className="label">Код алгоритма</label>
            <input
              className="input"
              value={form.code}
              onChange={(e) => setForm({ ...form, code: e.target.value })}
              placeholder="БС-20"
            />
          </div>
          <div>
            <label className="label">Название</label>
            <input
              className="input"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </div>
          <div>
            <label className="label">Источник данных</label>
            <input
              className="input"
              value={form.source}
              onChange={(e) => setForm({ ...form, source: e.target.value })}
              placeholder="СФМ_ФМ1"
            />
          </div>
          <div>
            <label className="label">Балл приоритетности</label>
            <input
              type="number"
              className="input"
              value={form.priority_score}
              onChange={(e) => setForm({ ...form, priority_score: e.target.value })}
            />
          </div>
          <div>
            <label className="label">Таблица результата в ClickHouse</label>
            <input
              className="input font-mono text-xs"
              value={form.clickhouse_result_table}
              onChange={(e) => setForm({ ...form, clickhouse_result_table: e.target.value })}
              placeholder="AFM_6_TEST.AFM_6_1_26"
            />
          </div>
          <div>
            <label className="label">Зависит от алгоритмов (через запятую)</label>
            <input
              className="input"
              value={form.depends_on}
              onChange={(e) => setForm({ ...form, depends_on: e.target.value })}
              placeholder="БС-1, БС-3"
            />
          </div>
          <div className="sm:col-span-2">
            <label className="label">Описание логики</label>
            <textarea
              className="input h-24"
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
            />
          </div>
          <div className="sm:col-span-2">
            <label className="label">SQL код</label>
            <textarea
              className="input h-72 font-mono text-xs"
              value={form.sql_script}
              onChange={(e) => setForm({ ...form, sql_script: e.target.value })}
              spellCheck={false}
            />
          </div>
        </div>
      </Modal>

      {/* --- обновление через ИИ --- */}
      <Modal
        open={Boolean(aiTarget)}
        title={aiTarget ? `Обновление SQL через ИИ: ${aiTarget.code}` : ''}
        onClose={closeAi}
        size="full"
        footer={
          aiResult ? (
            <>
              <button type="button" className="btn-secondary" onClick={closeAi}>
                Отклонить
              </button>
              <button
                type="button"
                className="btn-primary"
                onClick={approveAiUpdate}
                disabled={busy === aiTarget?.code}
              >
                {busy === aiTarget?.code && <Spinner className="h-4 w-4" />}
                Одобрить и выполнить
              </button>
            </>
          ) : (
            <>
              <button type="button" className="btn-secondary" onClick={closeAi}>
                Отмена
              </button>
              <button
                type="button"
                className="btn-primary"
                onClick={requestAiUpdate}
                disabled={aiLoading}
              >
                {aiLoading && <Spinner className="h-4 w-4" />}
                {aiLoading ? 'Модель работает…' : 'Получить предложение'}
              </button>
            </>
          )
        }
      >
        {aiTarget && (
          <div className="space-y-4">
            {!aiResult && (
              <>
                <InfoMessage>
                  Модели будут переданы структуры используемых таблиц, действующий SQL и ваше
                  требование. Предложение вступит в силу только после вашего одобрения.
                </InfoMessage>
                <div>
                  <label className="label">Новое бизнес-требование</label>
                  <textarea
                    className="input h-40"
                    value={aiRequirement}
                    onChange={(e) => setAiRequirement(e.target.value)}
                    placeholder="Например: увеличить порог суммы операций с 10 до 25 миллионов тенге и добавить исключение для страховых организаций"
                  />
                </div>
              </>
            )}

            {aiError && <ErrorMessage message={aiError} />}

            {aiLoading && <Loading text="Модель формирует новый SQL, это может занять несколько минут…" />}

            {aiResult && (
              <>
                <InfoMessage tone="warning">
                  Проверьте предложенный SQL перед применением. После одобрения прежняя версия
                  сохранится в истории, а новый запрос будет выполнен в ClickHouse.
                </InfoMessage>

                {aiResult.tables?.length > 0 && (
                  <div className="text-xs text-slate-500">
                    Модели переданы структуры таблиц: {aiResult.tables.join(', ')}
                  </div>
                )}

                <DiffView oldSql={aiResult.old_sql} newSql={aiResult.new_sql} />

                <details>
                  <summary className="cursor-pointer text-xs font-medium text-slate-600">
                    Показать предложенный SQL целиком
                  </summary>
                  <pre className="mt-2 overflow-x-auto rounded border border-slate-200 bg-slate-50 p-3 font-mono text-xs text-slate-700">
                    {aiResult.new_sql}
                  </pre>
                </details>
              </>
            )}
          </div>
        )}
      </Modal>
    </div>
  )
}
