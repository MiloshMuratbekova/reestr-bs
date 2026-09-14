import { useEffect, useState } from 'react'
import { errorMessage, registryApi } from '../api/client.js'
import { ErrorMessage, InfoMessage, Loading } from './ui.jsx'
import { AssetsBlock, FinmonBlock, RisksBlock } from './portraitBlocks.jsx'

/** Портрет организации: активы и операции финмониторинга по её БИН.
 *
 *  Блоки те же, что и в портрете лица: витрины различают стороны сделки
 *  по идентификатору, а не по виду лица. Доходов, прописки и особых
 *  учётов здесь нет — они о человеке.
 */
export default function CompanyPortrait({ bin }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  // У иностранной компании вместо БИН составной ключ с наименованием,
  // искать по нему в витринах нечего
  const realBin = /^[0-9]{12}$/.test(String(bin || '')) ? String(bin) : ''

  useEffect(() => {
    if (!realBin) return undefined
    let cancelled = false
    setLoading(true)
    setError('')
    registryApi
      .companyPortrait(realBin)
      .then(({ data: payload }) => {
        if (!cancelled) setData(payload)
      })
      .catch((err) => {
        if (!cancelled) setError(errorMessage(err, 'Портрет организации не загружен'))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [realBin])

  if (!realBin) {
    return (
      <section className="card">
        <div className="card-header">
          <h2 className="card-title">Активы и операции</h2>
        </div>
        <InfoMessage>
          Сведения ищутся по БИН. У этой организации его нет — искать
          в витринах нечего.
        </InfoMessage>
      </section>
    )
  }

  return (
    <section className="card">
      <div className="card-header">
        <h2 className="card-title">Активы и операции</h2>
        {data?.finmon?.messages?.length > 0 && (
          <span className="text-xs text-slate-500">
            операций финмониторинга: {data.finmon.messages.length}
          </span>
        )}
      </div>

      {loading && <Loading text="Собираем сведения по организации…" />}
      {error && <ErrorMessage message={error} />}

      {data && !loading && !error && (
        <div className="space-y-3">
          <RisksBlock risks={data.risks} />
          <AssetsBlock assets={data.assets} />
          <FinmonBlock finmon={data.finmon} />
        </div>
      )}
    </section>
  )
}
