import { useEffect, useRef, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { errorMessage, registryApi } from '../api/client.js'
import {
  AlgorithmChips,
  DASH,
  EmptyState,
  ErrorMessage,
  Field,
  InfoMessage,
  Loading,
  ProbabilityBar,
  Spinner,
  StatusBadge,
  riskStyle,
  isCompanyBin,
  value,
} from '../components/ui.jsx'

const QUICK_QUESTIONS = [
  'Кто конечный бенефициар этой компании?',
  'Какие риски связаны с этой компанией?',
  'Почему бенефициары определены именно так?',
  'Что нужно проверить дополнительно?',
]

/* -------------------------------------------------------------------------- */
/* Блок: информация о компании                                                */
/* -------------------------------------------------------------------------- */
function CompanyBlock({ company, beneficiaryCount, maxBall3 }) {
  const style = riskStyle(maxBall3)

  return (
    <section className="card">
      <div className="card-header">
        <h2 className="card-title">Информация о компании</h2>
        {company.is_state_owned && (
          <span className="badge bg-slate-200 text-slate-700">Государственная собственность</span>
        )}
        {company.is_unknown && (
          <span className="badge bg-amber-100 text-amber-900">Нет в справочнике ЮЛ</span>
        )}
      </div>

      <div className="p-5">
        <h1 className="text-lg font-semibold text-slate-900">{value(company.taxpayer_name)}</h1>

        {company.is_unknown && (
          <p className="mt-1 text-xs text-slate-500">
            Реквизиты недоступны: компании нет в справочнике юридических лиц —
            так бывает у иностранных организаций. Наименование восстановлено
            по сведениям алгоритмов.
          </p>
        )}

        <dl className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="БИН">
            <span className="font-mono">{value(company.taxpayer_iin_bin)}</span>
          </Field>
          <Field label="Организационно-правовая форма">{value(company.category)}</Field>
          <Field label="Тип собственности">{value(company.ownership_type)}</Field>
          <Field label="Дата регистрации">{value(company.reg_start_date)}</Field>
          <Field label="Код региона">{value(company.code_nd)}</Field>
          <Field label="Адрес">{value(company.address)}</Field>
          <Field label="Выявлено бенефициаров">{beneficiaryCount}</Field>
          <Field label="Максимальная вероятность">
            <span className={`font-semibold ${style.text}`}>
              {Number(maxBall3 || 0).toFixed(2)}%
            </span>
          </Field>
        </dl>
      </div>
    </section>
  )
}

/* -------------------------------------------------------------------------- */
/* Блок: карточка одного бенефициара                                          */
/* -------------------------------------------------------------------------- */
function BeneficiaryCard({ item, onExplain, explaining }) {
  const style = riskStyle(item.ball3)

  return (
    <div className={`rounded-lg border p-4 ${style.card}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          {/* Бенефициар-юрлицо ведёт на свою карточку: она теперь строится
              и для компаний, которых нет в справочнике ЮЛ */}
          {isCompanyBin(item.benefeciary_iin_bin) ? (
            <Link
              to={`/company/${encodeURIComponent(item.benefeciary_iin_bin)}`}
              className="text-sm font-semibold text-afm-700 hover:underline"
            >
              {value(item.benefeciary_name)}
            </Link>
          ) : (
            <div className="text-sm font-semibold text-slate-900">
              {value(item.benefeciary_name)}
            </div>
          )}
          <div className="mt-0.5 text-xs text-slate-600">
            ИИН: <span className="font-mono">{value(item.benefeciary_iin_bin)}</span>
          </div>
        </div>
        <StatusBadge status={item.status} />
      </div>

      <dl className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Field label="Алгоритмы">
          <AlgorithmChips codes={item.algorithm_codes} />
        </Field>
        <Field label="Доля владения">{value(item.share_percentage)}</Field>
        <Field label="Баллы (ball2 / ball1)">
          {item.ball2 ?? 0} / {item.ball1 ?? 0}
        </Field>
        <Field label="Документ">{value(item.document_info)}</Field>
      </dl>

      <div className="mt-3">
        <ProbabilityBar value={item.ball3} />
      </div>

      {item.dop_info && (
        <div className="mt-3 rounded border border-white/60 bg-white/70 px-3 py-2 text-xs text-slate-700">
          <span className="font-medium">Дополнительная информация: </span>
          {item.dop_info}
        </div>
      )}

      <div className="mt-3 flex items-center justify-between gap-3 text-xs text-slate-500">
        <span>Актуальность: {value(item._actual_date)}</span>
        <button
          type="button"
          className="btn-secondary px-3 py-1 text-xs"
          onClick={() => onExplain(item)}
          disabled={explaining}
        >
          {explaining && <Spinner className="h-3 w-3" />}
          Объяснить
        </button>
      </div>
    </div>
  )
}

/* -------------------------------------------------------------------------- */
/* Блок: бенефициарные собственники                                           */
/* -------------------------------------------------------------------------- */
function BeneficiariesBlock({ card, onExplain, explainingIin }) {
  const { beneficiaries, warning } = card

  return (
    <section className="card">
      <div className="card-header">
        <h2 className="card-title">Бенефициарные собственники</h2>
        <span className="text-xs text-slate-500">Всего: {beneficiaries.length}</span>
      </div>

      <div className="p-5">
        {warning ? (
          <InfoMessage tone="warning">{warning}</InfoMessage>
        ) : beneficiaries.length === 0 ? (
          <EmptyState
            title="Бенефициарные собственники не выявлены"
            description="Ни один из алгоритмов не дал результата по этой компании"
          />
        ) : (
          <div className="space-y-3">
            {beneficiaries.map((item, index) => (
              <BeneficiaryCard
                key={`${item.benefeciary_key}-${index}`}
                item={item}
                onExplain={onExplain}
                explaining={explainingIin === item.benefeciary_key}
              />
            ))}
          </div>
        )}
      </div>
    </section>
  )
}

/* -------------------------------------------------------------------------- */
/* Блок: объяснение ИИ                                                        */
/* -------------------------------------------------------------------------- */
function ExplainBlock({ bin, explanation, setExplanation, disabled }) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleExplain = async () => {
    setLoading(true)
    setError('')
    try {
      const { data } = await registryApi.explain(bin)
      setExplanation(data.explanation)
    } catch (err) {
      setError(errorMessage(err, 'Модель не смогла подготовить объяснение'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="card">
      <div className="card-header">
        <h2 className="card-title">Объяснение ИИ</h2>
        <button
          type="button"
          className="btn-primary px-3 py-1.5 text-xs"
          onClick={handleExplain}
          disabled={loading || disabled}
        >
          {loading && <Spinner className="h-3.5 w-3.5" />}
          {loading ? 'Модель анализирует…' : 'Получить объяснение'}
        </button>
      </div>

      <div className="p-5">
        {error && <ErrorMessage message={error} />}

        {!error && !explanation && !loading && (
          <p className="text-sm text-slate-500">
            {disabled
              ? 'Для государственных компаний бенефициарные собственники не определяются.'
              : 'Нажмите «Получить объяснение», чтобы модель Qwen пояснила результат простыми словами.'}
          </p>
        )}

        {loading && <Loading text="Модель формирует объяснение, это может занять до минуты…" />}

        {explanation && !loading && (
          <div className="whitespace-pre-wrap text-sm leading-relaxed text-slate-700">
            {explanation}
          </div>
        )}
      </div>
    </section>
  )
}

/* -------------------------------------------------------------------------- */
/* Блок: чат с аналитическим помощником                                       */
/* -------------------------------------------------------------------------- */
function ChatBlock({ bin }) {
  const [history, setHistory] = useState([])
  const [message, setMessage] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const endRef = useRef(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [history, loading])

  const send = async (text) => {
    const question = (text ?? message).trim()
    if (!question || loading) return

    setHistory((prev) => [...prev, { role: 'user', content: question }])
    setMessage('')
    setLoading(true)
    setError('')

    try {
      const { data } = await registryApi.chat(bin, question)
      setHistory((prev) => [...prev, { role: 'assistant', content: data.answer }])
    } catch (err) {
      setError(errorMessage(err, 'Модель не ответила на вопрос'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="card">
      <div className="card-header">
        <h2 className="card-title">Вопрос аналитика</h2>
      </div>

      <div className="p-5">
        <div className="mb-3 flex flex-wrap gap-2">
          {QUICK_QUESTIONS.map((question) => (
            <button
              key={question}
              type="button"
              className="btn-secondary px-2.5 py-1 text-xs"
              onClick={() => send(question)}
              disabled={loading}
            >
              {question}
            </button>
          ))}
        </div>

        <div className="mb-3 max-h-96 space-y-3 overflow-y-auto rounded-md border border-slate-200 bg-slate-50 p-3">
          {history.length === 0 && !loading && (
            <p className="py-6 text-center text-sm text-slate-400">
              Задайте вопрос о компании — ответ будет построен на данных реестра
            </p>
          )}

          {history.map((entry, index) => (
            <div
              key={index}
              className={`flex ${entry.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-[85%] whitespace-pre-wrap rounded-lg px-3 py-2 text-sm ${
                  entry.role === 'user'
                    ? 'bg-afm-600 text-white'
                    : 'border border-slate-200 bg-white text-slate-700'
                }`}
              >
                {entry.content}
              </div>
            </div>
          ))}

          {loading && (
            <div className="flex items-center gap-2 text-sm text-slate-500">
              <Spinner className="h-4 w-4" />
              Модель готовит ответ…
            </div>
          )}

          <div ref={endRef} />
        </div>

        {error && <ErrorMessage message={error} />}

        <form
          onSubmit={(event) => {
            event.preventDefault()
            send()
          }}
          className="mt-3 flex gap-2"
        >
          <input
            className="input flex-1"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder="Введите вопрос…"
            disabled={loading}
          />
          <button type="submit" className="btn-primary" disabled={loading || !message.trim()}>
            Отправить
          </button>
        </form>
      </div>
    </section>
  )
}

/* -------------------------------------------------------------------------- */
/* Блок: учредители и руководитель                                            */
/* -------------------------------------------------------------------------- */
function FoundersBlock({ founders, directors }) {
  return (
    <section className="card">
      <div className="card-header">
        <h2 className="card-title">Учредители и руководитель</h2>
      </div>

      <div className="p-5">
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
          Руководитель
        </h3>
        {directors.length === 0 ? (
          <p className="text-sm text-slate-400">{DASH}</p>
        ) : (
          <ul className="mb-5 space-y-1">
            {directors.map((director, index) => (
              <li key={index} className="text-sm text-slate-700">
                {value(director.director_name)}{' '}
                <span className="font-mono text-xs text-slate-500">
                  ({value(director.director_iin_bin)})
                </span>
              </li>
            ))}
          </ul>
        )}

        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
          Учредители
        </h3>
        {founders.length === 0 ? (
          <p className="text-sm text-slate-400">{DASH}</p>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Наименование / ФИО</th>
                  <th>ИИН / БИН</th>
                  <th>Доля, %</th>
                </tr>
              </thead>
              <tbody>
                {founders.map((founder, index) => (
                  <tr key={index}>
                    <td>{value(founder.founder_name)}</td>
                    <td className="font-mono text-xs">{value(founder.founder_iin_bin)}</td>
                    <td>{value(founder.share_percentage)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  )
}

/* -------------------------------------------------------------------------- */
/* Страница                                                                   */
/* -------------------------------------------------------------------------- */
export default function CompanyPage() {
  const { bin } = useParams()
  const [searchParams] = useSearchParams()

  const [card, setCard] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [explanation, setExplanation] = useState('')
  const [explainingIin, setExplainingIin] = useState('')

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      const { data } = await registryApi.company(bin)
      setCard(data)
    } catch (err) {
      setError(errorMessage(err, 'Не удалось загрузить карточку компании'))
      setCard(null)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    setExplanation('')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bin])

  const explainBeneficiary = async (item) => {
    setExplainingIin(item.benefeciary_key)
    try {
      const { data } = await registryApi.explain(bin, item.benefeciary_key)
      setExplanation(data.explanation)
      window.scrollTo({ top: document.body.scrollHeight / 2, behavior: 'smooth' })
    } catch (err) {
      setError(errorMessage(err, 'Модель не смогла подготовить объяснение'))
    } finally {
      setExplainingIin('')
    }
  }

  const backLink = `/search${searchParams.toString() ? `?${searchParams.toString()}` : ''}`

  if (loading) return <Loading text="Расчёт бенефициарных собственников…" />

  if (error && !card) {
    return (
      <div className="space-y-4">
        <Link to={backLink} className="text-sm text-afm-600 hover:underline">
          ← Вернуться к поиску
        </Link>
        <ErrorMessage message={error} onRetry={load} />
      </div>
    )
  }

  if (!card) return null

  return (
    <div className="space-y-5">
      <Link to={backLink} className="inline-block text-sm text-afm-600 hover:underline">
        ← Вернуться к поиску
      </Link>

      {error && <ErrorMessage message={error} />}

      <CompanyBlock
        company={card.company}
        beneficiaryCount={card.beneficiary_count}
        maxBall3={card.max_ball3}
      />

      <BeneficiariesBlock
        card={card}
        onExplain={explainBeneficiary}
        explainingIin={explainingIin}
      />

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
        <ExplainBlock
          bin={bin}
          explanation={explanation}
          setExplanation={setExplanation}
          disabled={card.company.is_state_owned}
        />
        <ChatBlock bin={bin} />
      </div>

      <FoundersBlock founders={card.founders} directors={card.directors} />
    </div>
  )
}
