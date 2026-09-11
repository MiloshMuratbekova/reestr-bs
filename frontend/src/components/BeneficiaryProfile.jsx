import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { errorMessage, listingApi } from '../api/client.js'
import Portrait from './Portrait.jsx'
import {
  AlgorithmChips,
  ErrorMessage,
  Loading,
  StatusBadge,
  number,
  value,
} from './ui.jsx'

/** Боковая панель с профилем бенефициара.
 *
 * Вынесена из страницы списка, потому что открывается из двух мест:
 * из списка бенефициаров и из карточки компании. Держать две копии
 * значило бы чинить каждую правку дважды.
 */
export default function BeneficiaryProfile({ iin, onClose }) {
  const navigate = useNavigate()
  const [profile, setProfile] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [tab, setTab] = useState('companies')

  useEffect(() => {
    if (!iin) return undefined
    let cancelled = false
    setLoading(true)
    setError('')
    listingApi
      .beneficiary(iin)
      .then(({ data }) => {
        if (!cancelled) setProfile(data)
      })
      .catch((err) => {
        if (!cancelled) setError(errorMessage(err, 'Профиль не загружен'))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [iin])

  if (!iin) return null

  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      <div
        className="absolute inset-0 bg-slate-900/30"
        onClick={onClose}
        role="presentation"
      />
      <div className="relative flex h-full w-full max-w-2xl flex-col bg-white shadow-xl">
        <div className="flex items-start justify-between border-b border-slate-200 px-6 py-4">
          <div className="min-w-0">
            <div className="text-sm font-semibold text-slate-800">
              {value(profile?.benefeciary_name)}
            </div>
            <div className="font-mono text-xs text-slate-500">{value(iin)}</div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
            aria-label="Закрыть"
          >
            ✕
          </button>
        </div>

        {/* Две вкладки: компании, где лицо выявлено, и справка по витринам */}
        <div className="flex gap-1 border-b border-slate-200 px-6 pt-2">
          {[
            ['companies', 'Компании'],
            ['portrait', 'Портрет'],
          ].map(([key, label]) => (
            <button
              key={key}
              type="button"
              onClick={() => setTab(key)}
              className={`rounded-t px-3 py-2 text-sm ${
                tab === key
                  ? 'border-b-2 border-afm-600 font-medium text-afm-700'
                  : 'text-slate-500 hover:text-slate-700'
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-4">
          {tab === 'portrait' && <Portrait iin={iin} />}
          {tab === 'companies' && loading && <Loading text="Загрузка профиля…" />}
          {tab === 'companies' && error && <ErrorMessage message={error} />}

          {tab === 'companies' && !loading && profile && (
            <>
              <div className="mb-4 grid grid-cols-2 gap-3">
                <div className="rounded-md bg-slate-50 px-4 py-3">
                  <div className="text-xs uppercase tracking-wide text-slate-500">Компаний</div>
                  <div className="mt-1 text-xl font-semibold text-slate-800">
                    {number(profile.company_count)}
                  </div>
                </div>
              </div>

              <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                Компании, где выявлен бенефициаром
              </div>

              {profile.companies?.length ? (
                <div className="space-y-2">
                  {profile.companies.map((row) => {
                    return (
                      <button
                        key={`${row.taxpayer_key || row.taxpayer_iin_bin}-${row.algorithms}`}
                        type="button"
                        onClick={() =>
                          navigate(`/company/${encodeURIComponent(row.taxpayer_key || row.taxpayer_iin_bin)}`)
                        }
                        className="w-full rounded-md border border-slate-200 px-4 py-3 text-left transition-colors hover:bg-slate-50"
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <div className="truncate text-sm font-medium text-slate-800">
                              {value(row.taxpayer_name)}
                            </div>
                            <div className="font-mono text-xs text-slate-500">
                              {value(row.taxpayer_iin_bin)}
                            </div>
                          </div>
                        </div>
                        <div className="mt-2 flex flex-wrap items-center gap-2">
                          <StatusBadge status={row.status} />
                          <AlgorithmChips
                            codes={row.algorithm_codes}
                            details={row.algorithm_details}
                          />
                        </div>
                        {row.dop_info && (
                          <div className="mt-2 line-clamp-2 text-xs text-slate-500">
                            {row.dop_info}
                          </div>
                        )}
                      </button>
                    )
                  })}
                </div>
              ) : (
                <EmptyState title="Компании не найдены" />
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
