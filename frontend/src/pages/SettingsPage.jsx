import { useCallback, useEffect, useState } from 'react'
import { errorMessage, settingsApi } from '../api/client.js'
import { ErrorMessage, InfoMessage, Loading, Spinner } from '../components/ui.jsx'

/**
 * Настройки подключений и лимитов.
 *
 * Важно помнить: сохранённое здесь СИЛЬНЕЕ значений из docker-compose и .env.
 * Если адрес поменяли в compose, а система ходит по старому — смотреть надо
 * в сохранённые настройки, а не в переменные окружения.
 */

const LIMIT_FIELDS = [
  {
    key: 'OLLAMA_NUM_CTX',
    label: 'Размер контекста модели',
    unit: 'токенов',
    hint:
      'Больше — модель видит за раз больше данных о компании, но растёт расход памяти ' +
      'на сервере ИИ и время ответа. Меньше — отвечает быстрее, но объёмная карточка ' +
      'может не поместиться целиком, и часть бенефициаров останется без внимания.',
  },
  {
    key: 'LLM_MAX_TOKENS',
    label: 'Длина ответа модели',
    unit: 'токенов',
    hint:
      'Больше — развёрнутые объяснения по всем четырём пунктам, дольше ожидание. ' +
      'Меньше — ответ быстрее, но может оборваться на середине фразы.',
  },
  {
    key: 'LLM_CONCURRENCY',
    label: 'Параллельных запросов к модели',
    unit: 'запросов',
    hint:
      'Больше — несколько аналитиков получают ответы одновременно. Но модель на 122 млрд ' +
      'параметров при параллельных запросах упирается в память и замедляется для всех сразу. ' +
      'Меньше — запросы встают в очередь, зато каждый обрабатывается на полной скорости.',
  },
  {
    key: 'OLLAMA_TIMEOUT',
    label: 'Таймаут запроса к модели',
    unit: 'секунд',
    hint:
      'Больше — тяжёлые запросы успевают завершиться. Меньше — быстрее видно, что сервер ИИ ' +
      'недоступен, но длинные объяснения будут обрываться по таймауту.',
  },
  {
    key: 'OLLAMA_TEMPERATURE',
    label: 'Температура',
    unit: '',
    step: '0.05',
    hint:
      'Выше — формулировки разнообразнее, но растёт риск, что модель домыслит то, чего нет ' +
      'в данных. Ниже — ответы предсказуемее и ближе к переданным сведениям. ' +
      'Для аналитики рекомендуется 0.1–0.3.',
  },
  {
    key: 'MAX_ROWS_PER_QUERY',
    label: 'Максимум строк в выборке',
    unit: 'строк',
    hint:
      'Больше — поиск показывает больше компаний за раз, но запрос к ClickHouse тяжелее. ' +
      'Меньше — отклик быстрее, зато результат обрезается и нужная компания может не попасть в список.',
  },
  {
    key: 'MAX_ROWS_PER_CLIENT',
    label: 'Строк данных на одного клиента',
    unit: 'строк',
    hint:
      'Больше — в карточке компании показываются все выявленные бенефициары. Меньше — экономия ' +
      'памяти сервера, но список бенефициаров может оказаться неполным.',
  },
  {
    key: 'CLICKHOUSE_MAX_EXECUTION_TIME',
    label: 'Таймаут тяжёлого сканирования базы',
    unit: 'секунд',
    hint:
      'Больше — объёмные алгоритмы (БС-13 по ЭСФ, это сотни миллионов строк) успевают досчитать. ' +
      'Меньше — зависшие запросы снимаются быстрее и не занимают ClickHouse, но расчёт может ' +
      'не завершиться и алгоритм упадёт по таймауту.',
  },
]

/* -------------------------------------------------------------------------- */
function StatusLine({ state }) {
  if (!state) return null
  if (state.pending) {
    return (
      <span className="inline-flex items-center gap-2 text-xs text-slate-500">
        <Spinner className="h-3.5 w-3.5" />
        Проверяю…
      </span>
    )
  }
  if (state.ok) {
    return (
      <span className="text-xs text-emerald-700">✓ {state.message || 'Подключение установлено'}</span>
    )
  }
  return <span className="text-xs text-red-700">✕ {state.error || 'Не удалось подключиться'}</span>
}

function Field({ label, children, hint }) {
  return (
    <div>
      <label className="label">{label}</label>
      {children}
      {hint && <p className="mt-1 text-xs leading-relaxed text-slate-500">{hint}</p>}
    </div>
  )
}

function Section({ title, source, children, footer }) {
  return (
    <section className="card">
      <div className="card-header">
        <h2 className="card-title">{title}</h2>
        {source && <span className="text-xs text-slate-400">{source}</span>}
      </div>
      <div className="space-y-4 p-5">{children}</div>
      {footer && (
        <div className="flex flex-wrap items-center gap-3 border-t border-slate-200 px-5 py-3">
          {footer}
        </div>
      )}
    </section>
  )
}

/* -------------------------------------------------------------------------- */
export default function SettingsPage() {
  const [values, setValues] = useState(null)
  const [source, setSource] = useState({})
  const [limits, setLimits] = useState({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [saving, setSaving] = useState(false)

  const [chState, setChState] = useState(null)
  const [pgState, setPgState] = useState(null)
  const [llmState, setLlmState] = useState(null)

  const [models, setModels] = useState([])
  const [modelsError, setModelsError] = useState('')
  const [modelsLoading, setModelsLoading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const { data } = await settingsApi.get()
      setValues(data.values)
      setSource(data.source || {})
      setLimits(data.limits || {})
    } catch (err) {
      setError(errorMessage(err, 'Не удалось загрузить настройки'))
    } finally {
      setLoading(false)
    }
  }, [])

  const loadModels = useCallback(async () => {
    setModelsLoading(true)
    setModelsError('')
    try {
      const { data } = await settingsApi.models()
      setModels(data.models || [])
      if (!data.ok) {
        // Список всё равно заполняется сохранённым перечнем — выбрать модель можно
        setModelsError(
          `Сервер ИИ недоступен (${data.error || 'нет связи'}). Показан сохранённый перечень.`,
        )
      }
    } catch (err) {
      setModelsError(errorMessage(err, 'Не удалось получить список моделей'))
    } finally {
      setModelsLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
    loadModels()
  }, [load, loadModels])

  const set = (key) => (event) => {
    const raw = event.target.value
    setValues((prev) => ({ ...prev, [key]: raw }))
  }

  const save = async () => {
    setSaving(true)
    setError('')
    setNotice('')
    try {
      // Пустые пароли не отправляем: пустое поле не должно затирать сохранённый
      const payload = { ...values }
      Object.keys(payload).forEach((key) => {
        if (key.endsWith('_SET')) delete payload[key]
      })
      if (!payload.CLICKHOUSE_PASSWORD) delete payload.CLICKHOUSE_PASSWORD
      if (!payload.POSTGRES_PASSWORD) delete payload.POSTGRES_PASSWORD

      const { data } = await settingsApi.save(payload)
      setValues(data.values)
      setSource(data.source || {})

      let text = `Сохранено параметров: ${data.applied.length}. Настройки применены без перезапуска.`
      if (data.ignored?.length) {
        text += ` Отброшены неизвестные ключи: ${data.ignored.join(', ')}.`
      }
      setNotice(text)
    } catch (err) {
      setError(errorMessage(err, 'Не удалось сохранить настройки'))
    } finally {
      setSaving(false)
    }
  }

  const runTest = async (kind) => {
    const setter = { ch: setChState, pg: setPgState, llm: setLlmState }[kind]
    setter({ pending: true })
    try {
      let response
      if (kind === 'ch') {
        response = await settingsApi.testClickHouse({
          host: values.CLICKHOUSE_HOST,
          port: Number(values.CLICKHOUSE_PORT),
          database: values.CLICKHOUSE_DATABASE,
          user: values.CLICKHOUSE_USER,
          password: values.CLICKHOUSE_PASSWORD || null,
        })
      } else if (kind === 'pg') {
        response = await settingsApi.testPostgres({
          host: values.POSTGRES_HOST,
          port: Number(values.POSTGRES_PORT),
          database: values.POSTGRES_DB,
          user: values.POSTGRES_USER,
          password: values.POSTGRES_PASSWORD || null,
        })
      } else {
        response = await settingsApi.testLlm()
      }
      const data = response.data
      setter({
        ok: data.ok,
        message: data.ok ? data.message || data.answer : '',
        error: data.error,
      })
    } catch (err) {
      setter({ ok: false, error: errorMessage(err, 'Проверка не выполнена') })
    }
  }

  if (loading) return <Loading text="Загрузка настроек…" />
  if (!values) return <ErrorMessage message={error} onRetry={load} />

  const sourceLabel = (keys) =>
    keys.some((k) => source[k] === 'file') ? 'изменено через интерфейс' : 'из окружения'

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-lg font-semibold text-slate-800">Настройки</h1>
        <p className="mt-0.5 text-sm text-slate-500">
          Адреса подключений и лимиты. Изменения применяются сразу, перезапуск не требуется.
        </p>
      </div>

      <InfoMessage tone="warning">
        Сохранённые здесь значения <strong>сильнее</strong> параметров из <code>docker-compose.yml</code>{' '}
        и <code>.env</code>. Если адрес поменяли в compose, контейнер перезапустили, а система
        продолжает ходить по-старому — причина здесь, а не в окружении. Пометка «изменено через
        интерфейс» у блока показывает, что значение взято из сохранённых настроек.
      </InfoMessage>

      {notice && <InfoMessage tone="success">{notice}</InfoMessage>}
      {error && <ErrorMessage message={error} />}

      {/* ---------------- ClickHouse ---------------- */}
      <Section
        title="ClickHouse — хранилище данных"
        source={sourceLabel([
          'CLICKHOUSE_HOST',
          'CLICKHOUSE_PORT',
          'CLICKHOUSE_DATABASE',
          'CLICKHOUSE_USER',
          'CLICKHOUSE_PASSWORD',
        ])}
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={() => runTest('ch')}>
              Проверить подключение к ClickHouse
            </button>
            <StatusLine state={chState} />
          </>
        }
      >
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Field label="Хост">
            <input className="input" value={values.CLICKHOUSE_HOST || ''} onChange={set('CLICKHOUSE_HOST')} />
          </Field>
          <Field label="Порт">
            <input type="number" className="input" value={values.CLICKHOUSE_PORT ?? ''} onChange={set('CLICKHOUSE_PORT')} />
          </Field>
          <Field label="База данных">
            <input className="input" value={values.CLICKHOUSE_DATABASE || ''} onChange={set('CLICKHOUSE_DATABASE')} />
          </Field>
          <Field label="Пользователь">
            <input className="input" value={values.CLICKHOUSE_USER || ''} onChange={set('CLICKHOUSE_USER')} />
          </Field>
          <Field
            label="Пароль"
            hint={
              values.CLICKHOUSE_PASSWORD_SET
                ? 'Пароль задан. Оставьте поле пустым, чтобы сохранить текущий.'
                : 'Пароль не задан.'
            }
          >
            <input
              type="password"
              className="input"
              placeholder={values.CLICKHOUSE_PASSWORD_SET ? '•••••••• (задан)' : 'не задан'}
              value={values.CLICKHOUSE_PASSWORD || ''}
              onChange={set('CLICKHOUSE_PASSWORD')}
              autoComplete="new-password"
            />
          </Field>
        </div>
      </Section>

      {/* ---------------- PostgreSQL ---------------- */}
      <Section
        title="PostgreSQL — метаданные системы"
        source={sourceLabel(['POSTGRES_HOST', 'POSTGRES_PORT', 'POSTGRES_DB', 'POSTGRES_USER'])}
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={() => runTest('pg')}>
              Проверить подключение к PostgreSQL
            </button>
            <StatusLine state={pgState} />
          </>
        }
      >
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Field label="Хост">
            <input className="input" value={values.POSTGRES_HOST || ''} onChange={set('POSTGRES_HOST')} />
          </Field>
          <Field label="Порт">
            <input type="number" className="input" value={values.POSTGRES_PORT ?? ''} onChange={set('POSTGRES_PORT')} />
          </Field>
          <Field label="База данных">
            <input className="input" value={values.POSTGRES_DB || ''} onChange={set('POSTGRES_DB')} />
          </Field>
          <Field label="Пользователь">
            <input className="input" value={values.POSTGRES_USER || ''} onChange={set('POSTGRES_USER')} />
          </Field>
          <Field
            label="Пароль"
            hint={
              values.POSTGRES_PASSWORD_SET
                ? 'Пароль задан. Оставьте поле пустым, чтобы сохранить текущий.'
                : 'Пароль не задан.'
            }
          >
            <input
              type="password"
              className="input"
              placeholder={values.POSTGRES_PASSWORD_SET ? '•••••••• (задан)' : 'не задан'}
              value={values.POSTGRES_PASSWORD || ''}
              onChange={set('POSTGRES_PASSWORD')}
              autoComplete="new-password"
            />
          </Field>
        </div>
      </Section>

      {/* ---------------- Модель ---------------- */}
      <Section
        title="Модель (ИИ)"
        source={sourceLabel(['OLLAMA_BASE_URL', 'OLLAMA_MODEL', 'LLM_API_KIND'])}
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={() => runTest('llm')}>
              Проверить
            </button>
            <StatusLine state={llmState} />
          </>
        }
      >
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Field label="Адрес сервера">
            <input className="input" value={values.OLLAMA_BASE_URL || ''} onChange={set('OLLAMA_BASE_URL')} />
          </Field>
          <Field
            label="Тип API"
            hint="Нативный Ollama — /api/generate. OpenAI-совместимый — /v1/chat/completions."
          >
            <select className="input" value={values.LLM_API_KIND || 'ollama'} onChange={set('LLM_API_KIND')}>
              <option value="ollama">Нативный Ollama</option>
              <option value="openai">OpenAI-совместимый</option>
            </select>
          </Field>
          <Field
            label="Держать модель в памяти"
            hint={
              'Сколько времени модель остаётся загруженной после запроса (например 30m, 2h, -1 — бессрочно). ' +
              'По умолчанию Ollama выгружает её через 5 минут, и первый запрос после паузы ждёт повторной ' +
              'загрузки — со стороны это выглядит как зависание. Больше — быстрее отклик, но память ' +
              'на сервере ИИ занята постоянно.'
            }
          >
            <input className="input" value={values.LLM_KEEP_ALIVE || ''} onChange={set('LLM_KEEP_ALIVE')} />
          </Field>
          <Field label="Модель">
            <div className="flex gap-2">
              <select className="input" value={values.OLLAMA_MODEL || ''} onChange={set('OLLAMA_MODEL')}>
                {!models.includes(values.OLLAMA_MODEL) && values.OLLAMA_MODEL && (
                  <option value={values.OLLAMA_MODEL}>{values.OLLAMA_MODEL}</option>
                )}
                {models.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
              <button
                type="button"
                className="btn-secondary whitespace-nowrap px-3"
                onClick={loadModels}
                disabled={modelsLoading}
              >
                {modelsLoading ? <Spinner className="h-4 w-4" /> : 'Обновить список'}
              </button>
            </div>
          </Field>
        </div>
        {modelsError && <p className="text-xs text-amber-700">{modelsError}</p>}
      </Section>

      {/* ---------------- Лимиты ---------------- */}
      <Section
        title="Лимиты"
        source={sourceLabel(LIMIT_FIELDS.map((f) => f.key))}
      >
        <InfoMessage>
          Все значения дополнительно ограничиваются на сервере. Если ввести число за пределами
          допустимого диапазона, оно будет автоматически приведено к границе — это защита от
          запроса, способного положить сервис.
        </InfoMessage>

        <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
          {LIMIT_FIELDS.map((field) => {
            const bounds = limits[field.key]
            return (
              <Field
                key={field.key}
                label={
                  <>
                    {field.label}
                    {field.unit ? `, ${field.unit}` : ''}
                  </>
                }
                hint={field.hint}
              >
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    step={field.step || '1'}
                    className="input"
                    value={values[field.key] ?? ''}
                    onChange={set(field.key)}
                  />
                  {bounds && (
                    <span className="whitespace-nowrap text-xs text-slate-400">
                      от {bounds.min} до {bounds.max}
                    </span>
                  )}
                </div>
              </Field>
            )
          })}
        </div>
      </Section>

      <div className="sticky bottom-0 flex items-center gap-3 border-t border-slate-200 bg-white/95 px-5 py-3 backdrop-blur">
        <button type="button" className="btn-primary" onClick={save} disabled={saving}>
          {saving && <Spinner className="h-4 w-4" />}
          {saving ? 'Сохраняю…' : 'Сохранить настройки'}
        </button>
        <button type="button" className="btn-secondary" onClick={load} disabled={saving}>
          Отменить изменения
        </button>
        <span className="text-xs text-slate-500">
          Применяется сразу: соединения пересоздаются без перезапуска контейнера.
        </span>
      </div>
    </div>
  )
}
