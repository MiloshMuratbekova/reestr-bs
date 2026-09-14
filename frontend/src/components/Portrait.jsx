import { useEffect, useState } from 'react'
import { errorMessage, registryApi } from '../api/client.js'
import { DASH, ErrorMessage, InfoMessage, Loading, number, value } from './ui.jsx'

/** Денежная сумма с разделителями разрядов. */
function money(raw) {
  const amount = Number(raw)
  if (!Number.isFinite(amount) || amount === 0) return DASH
  return `${amount.toLocaleString('ru-RU', { maximumFractionDigits: 0 })} ₸`
}

/** Блок портрета. Пустой блок при недоступной витрине и пустой блок при
 *  отсутствии сведений — разные вещи, поэтому подписаны они по-разному. */
function Block({ title, available, empty, children, hint }) {
  return (
    <section className="rounded-md border border-slate-200">
      <div className="flex items-center justify-between border-b border-slate-100 px-3 py-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-slate-600">
          {title}
        </span>
        {hint && <span className="text-[11px] text-slate-400">{hint}</span>}
      </div>
      <div className="px-3 py-2 text-xs">
        {available === false ? (
          <p className="text-slate-400">Витрина недоступна — сведения не запрашивались</p>
        ) : empty ? (
          <p className="text-slate-500">Сведений нет</p>
        ) : (
          children
        )}
      </div>
    </section>
  )
}

function Rows({ items, columns }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-xs">
        <thead>
          <tr className="text-slate-500">
            {columns.map((c) => (
              <th key={c.key} className="whitespace-nowrap py-1 pr-3 font-medium">
                {c.title}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {items.map((row, index) => (
            <tr key={index} className="border-t border-slate-100">
              {columns.map((c) => (
                <td key={c.key} className="py-1 pr-3 align-top">
                  {c.render ? c.render(row) : value(row[c.key])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** Портрет лица: справка из витрин по одному ИИН. */
export default function Portrait({ iin }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  // Портрет строится только по настоящему ИИН: у нерезидента с ключом
  // «нерезидент: имя» искать в витринах нечего
  const realIin = /^[0-9]{12}$/.test(String(iin || '')) ? String(iin) : ''

  useEffect(() => {
    if (!realIin) return undefined
    let cancelled = false
    setLoading(true)
    setError('')
    registryApi
      .portrait(realIin)
      .then(({ data: payload }) => {
        if (!cancelled) setData(payload)
      })
      .catch((err) => {
        if (!cancelled) setError(errorMessage(err, 'Портрет не загружен'))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [realIin])

  if (!realIin) {
    return (
      <InfoMessage>
        Портрет строится по ИИН. У этого лица идентификатора нет, искать
        в витринах нечего.
      </InfoMessage>
    )
  }
  if (loading) return <Loading text="Собираем портрет…" />
  if (error) return <ErrorMessage message={error} />
  if (!data) return null

  const { identity, income, assets, debts, finmon, risks, special } = data

  return (
    <div className="space-y-3">
      <Block title="Метки реестров риска" available={risks.available}
        empty={!risks.labels.length}>
        <div className="flex flex-wrap gap-1">
          {risks.labels.map((label) => (
            <span key={label} className="badge bg-amber-100 text-amber-900">
              {label}
            </span>
          ))}
        </div>
      </Block>

      <Block title="Адрес регистрации" available={identity.available}
        empty={!identity.address}>
        {identity.address && (
          <p>
            {[identity.address.country, identity.address.region, identity.address.city,
              identity.address.district, identity.address.micro_district,
              identity.address.house && `д. ${identity.address.house}`,
              identity.address.flat && `кв. ${identity.address.flat}`]
              .filter(Boolean)
              .join(', ')}
          </p>
        )}
        {(identity.same_flat?.length > 0 || identity.same_house?.length > 0) && (
          <div className="mt-2 space-y-1 text-slate-600">
            {identity.same_flat?.length > 0 && (
              <div>
                Та же квартира:{' '}
                <span className="font-mono">
                  {identity.same_flat.map((n) => n.iin).join(', ')}
                </span>
              </div>
            )}
            {identity.same_house?.length > 0 && (
              <div>
                Тот же дом:{' '}
                <span className="font-mono">
                  {identity.same_house.map((n) => n.iin).join(', ')}
                </span>
                {identity.is_apartment_house && (
                  <span className="ml-1 text-slate-400">
                    (многоквартирный дом — показаны только уже выявленные)
                  </span>
                )}
              </div>
            )}
          </div>
        )}
      </Block>

      <Block
        title="Доходы"
        available={income.available}
        empty={!income.pension.length && !income.salary.length && !income.government.length}
        hint={income.income_estimate ? `оценка по ОПВ: ${money(income.income_estimate)}` : ''}
      >
        {income.is_student && (
          <p className="mb-2 text-amber-700">Получал стипендию — учащийся</p>
        )}
        {income.government.length > 0 && (
          <p className="mb-2">
            Государственный служащий:{' '}
            {income.government.map((g) => g.organ).filter(Boolean).join(', ')}
          </p>
        )}
        {income.pension.length > 0 && (
          <Rows
            items={income.pension}
            columns={[
              { key: 'employer', title: 'Работодатель' },
              { key: 'payments', title: 'Взносов', render: (r) => number(r.payments) },
              { key: 'first_payment', title: 'Первый' },
              { key: 'last_payment', title: 'Последний' },
              { key: 'total_amount', title: 'Взносы', render: (r) => money(r.total_amount) },
              {
                key: 'income_estimate',
                title: 'Оценка дохода',
                render: (r) => money(r.income_estimate),
              },
            ]}
          />
        )}
        {income.salary.length > 0 && (
          <div className="mt-2">
            <Rows
              items={income.salary}
              columns={[
                { key: 'year', title: 'Год' },
                { key: 'quarter', title: 'Кв.' },
                { key: 'kind_name', title: 'Вид выплаты' },
                { key: 'kind_group', title: 'Группа' },
                { key: 'gross', title: 'Начислено', render: (r) => money(r.gross) },
                { key: 'net', title: 'На руки', render: (r) => money(r.net) },
              ]}
            />
          </div>
        )}
      </Block>

      <Block
        title="Активы"
        available={assets.available}
        empty={!assets.deals.length}
        hint={
          assets.purchased_total
            ? `приобретено на ${money(assets.purchased_total)}` +
              (assets.gifted_count ? `, в дар: ${assets.gifted_count}` : '')
            : ''
        }
      >
        <Rows
          items={assets.deals}
          columns={[
            { key: 'date', title: 'Дата' },
            { key: 'role', title: 'Роль' },
            { key: 'asset', title: 'Актив' },
            { key: 'oper', title: 'Операция' },
            { key: 'amount', title: 'Сумма', render: (r) => money(r.amount) },
            {
              key: 'is_gift',
              title: 'Основание',
              render: (r) => (r.is_gift ? 'дар / наследство' : 'приобретение'),
            },
          ]}
        />
      </Block>

      <Block title="Долги на исполнении" available={debts.available}
        empty={!debts.items.length}>
        <Rows
          items={debts.items}
          columns={[
            { key: 'started_at', title: 'Начато' },
            { key: 'creditor', title: 'Взыскатель' },
            { key: 'amount', title: 'Сумма', render: (r) => money(r.amount) },
            { key: 'category', title: 'Категория' },
            { key: 'travel_ban_date', title: 'Запрет выезда' },
          ]}
        />
      </Block>

      <Block
        title="Финансовый мониторинг"
        available={finmon.available}
        empty={!finmon.messages.length}
        hint={
          finmon.messages.length
            ? `операций: ${number(finmon.messages.length)}` +
              `, отправлено ${money(finmon.outgoing_total)}` +
              `, получено ${money(finmon.incoming_total)}` +
              `, подозрительных: ${number(finmon.suspicious_count)}`
            : ''
        }
      >
        {/* Операции разделены по направлению: по одному контрагенту нельзя
            понять, деньги ушли или пришли. Роли, где лицо лишь упомянуто,
            вынесены отдельно — приписывать им направление значило бы
            выдавать догадку за факт. */}
        {[
          ['outgoing', 'Отправлял', finmon.outgoing],
          ['incoming', 'Получал', finmon.incoming],
          ['other', 'Упомянут в операции', finmon.other],
        ]
          .filter(([, , items]) => items?.length)
          .map(([key, title, items]) => (
            <div key={key} className="mb-3 last:mb-0">
              <div className="mb-1 font-medium text-slate-600">
                {title} · {number(items.length)}
              </div>
              <Rows
                items={items.slice(0, 50)}
                columns={[
                  { key: 'date_oper', title: 'Дата' },
                  { key: 'oper_code', title: 'Код вида' },
                  { key: 'oper_kind', title: 'Вид операции' },
                  {
                    key: 'amount_tenge',
                    title: 'Сумма, ₸',
                    render: (r) => money(r.amount_tenge),
                  },
                  {
                    key: 'amount_currency',
                    title: 'В валюте',
                    render: (r) =>
                      Number(r.amount_currency)
                        ? `${Number(r.amount_currency).toLocaleString('ru-RU')} ${
                            r.currency_code || ''
                          }`
                        : DASH,
                  },
                  {
                    key: 'sender',
                    title: 'Отправитель',
                    render: (r) => (
                      <div>
                        <div>{value(r.sender_name)}</div>
                        <div className="font-mono text-[11px] text-slate-500">
                          {[r.sender_iin, r.sender_country, r.sender_bank_country]
                            .filter(Boolean)
                            .join(' · ')}
                        </div>
                      </div>
                    ),
                  },
                  {
                    key: 'receiver',
                    title: 'Получатель',
                    render: (r) => (
                      <div>
                        <div>{value(r.receiver_name)}</div>
                        <div className="font-mono text-[11px] text-slate-500">
                          {[r.receiver_iin, r.receiver_country, r.receiver_bank_country]
                            .filter(Boolean)
                            .join(' · ')}
                        </div>
                      </div>
                    ),
                  },
                  { key: 'susp', title: 'Признак' },
                  { key: 'cfm_name', title: 'Кто прислал' },
                ]}
              />
              {items.length > 50 && (
                <p className="mt-1 text-slate-400">
                  Показаны первые 50 из {number(items.length)}
                </p>
              )}
            </div>
          ))}
      </Block>

      <Block
        title="Особые учёты"
        available
        empty={
          !special.invalid &&
          !special.narco.length &&
          !special.destructive.length &&
          !special.special_records.length &&
          !special.erdr.length
        }
      >
        {special.invalid && (
          <p>
            Инвалидность: {value(special.invalid.group_name)}
            {special.invalid.capacity_loss && `, утрата ${special.invalid.capacity_loss}`}
            {special.invalid.monthly_payment &&
              `, выплата ${money(special.invalid.monthly_payment)}`}
          </p>
        )}
        {special.narco.length > 0 && <p>Наркоучёт: {special.narco.join(', ')}</p>}
        {special.destructive.length > 0 && (
          <p>Деструктивные течения: {special.destructive.join(', ')}</p>
        )}
        {special.special_records.length > 0 && (
          <p>
            Спецучёт:{' '}
            {special.special_records
              .map((r) => [r.name, r.status].filter(Boolean).join(' — '))
              .join('; ')}
          </p>
        )}
        {special.erdr.length > 0 && (
          <div className="mt-2">
            <div className="mb-1 font-medium text-slate-600">Досудебные расследования</div>
            <Rows
              items={special.erdr}
              columns={[
                { key: 'registered_at', title: 'Дата' },
                { key: 'qualification', title: 'Квалификация' },
                { key: 'description', title: 'Описание' },
              ]}
            />
          </div>
        )}
      </Block>
    </div>
  )
}
