/**
 * Настройки администратора — четыре вкладки.
 *
 * По ТЗ вкладок три: алгоритмы, пользователи, расписание. Четвёртой оставлены
 * подключения и лимиты (SettingsPage): их вынесли на фронт отдельной задачей,
 * и терять эту страницу нельзя. Содержимое вкладок — существующие страницы,
 * они не переписывались: каждая продолжает отвечать за свой раздел.
 */

import { useSearchParams } from 'react-router-dom'
import AlgorithmsPage from './AlgorithmsPage.jsx'
import SchedulePage from './SchedulePage.jsx'
import SettingsPage from './SettingsPage.jsx'
import UsersPage from './UsersPage.jsx'
import { useAuth } from '../context/AuthContext.jsx'
import { InfoMessage } from '../components/ui.jsx'

const TABS = [
  { key: 'connections', label: 'Подключения и лимиты', Component: SettingsPage },
  { key: 'algorithms', label: 'Алгоритмы', Component: AlgorithmsPage },
  { key: 'users', label: 'Пользователи', Component: UsersPage, needsAuth: true },
  { key: 'schedule', label: 'Расписание', Component: SchedulePage },
]

export default function SettingsHubPage() {
  const { authEnabled } = useAuth()
  const [searchParams, setSearchParams] = useSearchParams()

  const tabs = TABS.filter((tab) => !tab.needsAuth || authEnabled)
  const requested = searchParams.get('tab')
  const active = tabs.find((tab) => tab.key === requested) || tabs[0]
  const Active = active.Component

  const select = (key) => {
    const next = new URLSearchParams(searchParams)
    next.set('tab', key)
    setSearchParams(next, { replace: true })
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-1 border-b border-slate-200">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            type="button"
            onClick={() => select(tab.key)}
            className={`-mb-px border-b-2 px-4 py-2 text-sm font-medium transition-colors ${
              tab.key === active.key
                ? 'border-afm-600 text-afm-700'
                : 'border-transparent text-slate-500 hover:text-slate-700'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* При отключённом входе учётных записей не существует: пользователь
          служебный, и управлять здесь нечем */}
      {!authEnabled && (
        <InfoMessage>
          Вход в систему отключён (AUTH_ENABLED=false): все запросы выполняются от имени
          служебного администратора, вкладка «Пользователи» скрыта. Чтобы вернуть вход,
          поставьте AUTH_ENABLED=true в .env и перезапустите контейнер.
        </InfoMessage>
      )}

      <Active />
    </div>
  )
}
