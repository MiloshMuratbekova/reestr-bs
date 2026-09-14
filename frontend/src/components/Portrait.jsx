import { useEffect, useState } from 'react'
import { errorMessage, registryApi } from '../api/client.js'
import { ErrorMessage, InfoMessage, Loading, number, value } from './ui.jsx'
import {
  AssetsBlock,
  Block,
  FinmonBlock,
  RisksBlock,
  Rows,
  money,
} from './portraitBlocks.jsx'

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
      <RisksBlock risks={risks} />

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

      <AssetsBlock assets={assets} />

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

      <FinmonBlock finmon={finmon} />

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
