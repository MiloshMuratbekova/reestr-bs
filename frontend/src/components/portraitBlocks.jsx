/** Блоки, общие для портрета лица и портрета организации.
 *
 *  Витрины активов и финансового мониторинга различают стороны сделки по
 *  идентификатору, а не по виду лица, поэтому у человека и у организации
 *  это одни и те же сведения. Держать для них две верстки значило бы
 *  однажды поправить одну и забыть вторую.
 */
import { DASH, number, value } from './ui.jsx'

/** Денежная сумма с разделителями разрядов. */
export function money(raw) {
  const amount = Number(raw)
  if (!Number.isFinite(amount) || amount === 0) return DASH
  return `${amount.toLocaleString('ru-RU', { maximumFractionDigits: 0 })} ₸`
}

/** Блок портрета. Пустой блок при недоступной витрине и пустой блок при
 *  отсутствии сведений — разные вещи, поэтому подписаны они по-разному. */
export function Block({ title, available, empty, children, hint }) {
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

export function Rows({ items, columns }) {
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

/** Активы: все поля витрины, включая номер документа, примечание и источник.
 *
 *  Раньше показывались только дата, актив и сумма. Без номера документа
 *  сделку не найти в первоисточнике, без источника непонятно, чья это
 *  запись, а в примечании лежит основание — по нему и видно дарение.
 */
export function AssetsBlock({ assets }) {
  return (
    <Block
      title="Активы"
      available={assets.available}
      empty={!assets.deals?.length}
      hint={
        assets.purchased_total
          ? `приобретено на ${money(assets.purchased_total)}` +
            (assets.gifted_count ? `, в дар: ${assets.gifted_count}` : '')
          : ''
      }
    >
      <Rows
        items={assets.deals || []}
        columns={[
          { key: 'date', title: 'Дата' },
          { key: 'role', title: 'Роль' },
          { key: 'asset', title: 'Актив' },
          { key: 'oper', title: 'Операция' },
          { key: 'doc_number', title: 'Документ' },
          { key: 'amount', title: 'Сумма', render: (r) => money(r.amount) },
          {
            key: 'is_gift',
            title: 'Основание',
            render: (r) => (r.is_gift ? 'дар / наследство' : 'приобретение'),
          },
          {
            key: 'dop_info',
            title: 'Дополнительно',
            render: (r) => (
              <span className="block max-w-[22rem] whitespace-pre-wrap break-words">
                {value(r.dop_info)}
              </span>
            ),
          },
          { key: 'source', title: 'Источник' },
        ]}
      />
    </Block>
  )
}

/** Операции финмониторинга, разложенные по направлению.
 *
 *  Отправлял, получал и «лишь упомянут» разделены: по одному контрагенту
 *  нельзя понять, деньги ушли или пришли, а роли, где направление не
 *  задано, вынесены отдельно, чтобы не выдавать догадку за факт.
 */
export function FinmonBlock({ finmon, limit = 50 }) {
  return (
    <Block
      title="Финансовый мониторинг"
      available={finmon.available}
      empty={!finmon.messages?.length}
      hint={
        finmon.messages?.length
          ? `операций: ${number(finmon.messages.length)}` +
            `, отправлено ${money(finmon.outgoing_total)}` +
            `, получено ${money(finmon.incoming_total)}` +
            `, подозрительных: ${number(finmon.suspicious_count)}`
          : ''
      }
    >
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
              items={items.slice(0, limit)}
              columns={[
                { key: 'date_oper', title: 'Дата' },
                { key: 'oper_code', title: 'Код вида' },
                { key: 'oper_kind', title: 'Вид операции' },
                { key: 'amount_tenge', title: 'Сумма, ₸', render: (r) => money(r.amount_tenge) },
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
            {items.length > limit && (
              <p className="mt-1 text-slate-400">
                Показаны первые {limit} из {number(items.length)}
              </p>
            )}
          </div>
        ))}
    </Block>
  )
}

/** Метки реестров риска. */
export function RisksBlock({ risks }) {
  return (
    <Block title="Метки реестров риска" available={risks.available}
      empty={!risks.labels?.length}>
      <div className="flex flex-wrap gap-1">
        {(risks.labels || []).map((label) => (
          <span key={label} className="badge bg-amber-100 text-amber-900">
            {label}
          </span>
        ))}
      </div>
    </Block>
  )
}
