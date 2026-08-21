/**
 * Боковая панель навигации.
 *
 * Сворачивается до иконок; выбор запоминается в браузере, чтобы после
 * перезагрузки страница выглядела так же, как её оставили.
 *
 * Значки нарисованы прямо здесь: контур закрытый, подключать библиотеку
 * иконок неоткуда, а лишний файл шрифта — это лишние килобайты в образе.
 */

import { useEffect, useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'

const COLLAPSED_KEY = 'reestr_bs_sidebar_collapsed'

function Icon({ name, className = 'h-5 w-5' }) {
  const paths = {
    dashboard: 'M3 3h7v9H3V3zm0 11h7v7H3v-7zm9 0h9v7h-9v-7zm0-11h9v9h-9V3z',
    search: 'M10 3a7 7 0 105.29 11.71l4 4 1.42-1.42-4-4A7 7 0 0010 3zm0 2a5 5 0 110 10 5 5 0 010-10z',
    companies: 'M4 21V7l6-4 6 4v3h4v11h-6v-4h-4v4H4zm2-2h2v-2H6v2zm0-4h2v-2H6v2zm0-4h2V9H6v2zm4 8h2v-2h-2v2zm0-4h2v-2h-2v2zm0-4h2V9h-2v2zm0-4h2V5h-2v2zm8 12h2v-2h-2v2zm0-4h2v-2h-2v2z',
    people: 'M12 12a4 4 0 100-8 4 4 0 000 8zm0 2c-4.42 0-8 2.24-8 5v3h16v-3c0-2.76-3.58-5-8-5z',
    graph: 'M5 3a2 2 0 100 4 2 2 0 000-4zm14 0a2 2 0 100 4 2 2 0 000-4zM12 17a2 2 0 100 4 2 2 0 000-4zm-.75-3h1.5v-2.2l4.06-2.34-.75-1.3L12 10.3 7.94 8.16l-.75 1.3 4.06 2.34V14z',
    sources: 'M12 3c-4.42 0-8 1.34-8 3v12c0 1.66 3.58 3 8 3s8-1.34 8-3V6c0-1.66-3.58-3-8-3zm0 2c3.87 0 6 1.07 6 1s-2.13 1-6 1-6-.93-6-1 2.13-1 6-1zm6 13c0 .07-2.13 1-6 1s-6-.93-6-1v-2.23c1.5.77 3.7 1.23 6 1.23s4.5-.46 6-1.23V18zm0-4.5c0 .07-2.13 1-6 1s-6-.93-6-1v-2.23C7.5 12.04 9.7 12.5 12 12.5s4.5-.46 6-1.23v2.23z',
    reports: 'M6 2h8l4 4v16H6V2zm7 1.5V7h3.5L13 3.5zM8 12h8v2H8v-2zm0 4h8v2H8v-2zm0-8h4v2H8V8z',
    settings:
      'M12 8a4 4 0 100 8 4 4 0 000-8zm8.94 4a7.9 7.9 0 00-.12-1.34l2.03-1.58-2-3.46-2.4.96a8.1 8.1 0 00-2.32-1.34L15.7 2h-4l-.43 2.24a8.1 8.1 0 00-2.32 1.34l-2.4-.96-2 3.46 2.03 1.58a7.9 7.9 0 000 2.68L2.55 14.9l2 3.46 2.4-.96c.7.57 1.48 1.03 2.32 1.34L9.7 21h4l.43-2.24a8.1 8.1 0 002.32-1.34l2.4.96 2-3.46-2.03-1.58c.08-.44.12-.89.12-1.34z',
  }

  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className={className} aria-hidden="true">
      <path d={paths[name] || paths.dashboard} />
    </svg>
  )
}

const MENU = [
  { to: '/dashboard', label: 'Дашборд', icon: 'dashboard' },
  { to: '/search', label: 'Поиск', icon: 'search' },
  { to: '/companies', label: 'Список ЮЛ', icon: 'companies' },
  { to: '/beneficiaries', label: 'Список бенефициаров', icon: 'people' },
  { to: '/ownership', label: 'Структуры владения', icon: 'graph' },
  { to: '/sources', label: 'Источники данных', icon: 'sources' },
  { to: '/reports', label: 'Отчёты', icon: 'reports' },
  { to: '/settings', label: 'Настройки', icon: 'settings', adminOnly: true },
]

export default function Sidebar() {
  const { user, isAdministrator, authEnabled, logout } = useAuth()
  const navigate = useNavigate()
  const [collapsed, setCollapsed] = useState(
    () => localStorage.getItem(COLLAPSED_KEY) === '1',
  )

  useEffect(() => {
    localStorage.setItem(COLLAPSED_KEY, collapsed ? '1' : '0')
  }, [collapsed])

  const items = MENU.filter((item) => !item.adminOnly || isAdministrator)

  const handleLogout = () => {
    logout()
    navigate('/login', { replace: true })
  }

  return (
    <aside
      className={`flex shrink-0 flex-col bg-afm-900 text-afm-100 transition-all duration-200 ${
        collapsed ? 'w-16' : 'w-60'
      }`}
    >
      <div className="flex items-center gap-3 border-b border-white/10 px-3 py-4">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded bg-white/15 text-sm font-bold text-white">
          БС
        </div>
        {!collapsed && (
          <div className="min-w-0 leading-tight">
            <div className="truncate text-sm font-semibold text-white">Реестр БС</div>
            <div className="truncate text-[11px] text-afm-300">АФМ РК</div>
          </div>
        )}
      </div>

      <nav className="flex-1 space-y-1 overflow-y-auto p-2">
        {items.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            title={collapsed ? item.label : undefined}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors ${
                isActive
                  ? 'bg-afm-600 font-medium text-white'
                  : 'text-afm-200 hover:bg-white/10 hover:text-white'
              }`
            }
          >
            <Icon name={item.icon} className="h-5 w-5 shrink-0" />
            {!collapsed && <span className="truncate">{item.label}</span>}
          </NavLink>
        ))}
      </nav>

      <div className="border-t border-white/10 p-2">
        <button
          type="button"
          onClick={() => setCollapsed((value) => !value)}
          className="mb-2 flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm text-afm-200 transition-colors hover:bg-white/10 hover:text-white"
          title={collapsed ? 'Развернуть панель' : 'Свернуть панель'}
        >
          <svg viewBox="0 0 24 24" fill="currentColor" className="h-5 w-5 shrink-0">
            <path
              d={
                collapsed
                  ? 'M9 6l6 6-6 6V6z'
                  : 'M15 6l-6 6 6 6V6z'
              }
            />
          </svg>
          {!collapsed && <span>Свернуть</span>}
        </button>

        <div className={`rounded-md bg-white/5 px-3 py-2 ${collapsed ? 'text-center' : ''}`}>
          {collapsed ? (
            <div
              className="text-sm font-semibold text-white"
              title={`${user?.username || ''} — ${
                user?.role === 'administrator' ? 'Администратор' : 'Пользователь'
              }`}
            >
              {(user?.username || '?').slice(0, 1).toUpperCase()}
            </div>
          ) : (
            <>
              <div className="truncate text-sm font-medium text-white">{user?.username}</div>
              <div className="text-[11px] text-afm-300">
                {user?.role === 'administrator' ? 'Администратор' : 'Пользователь'}
              </div>
            </>
          )}
        </div>

        {/* Выход имеет смысл только когда вход включён: при AUTH_ENABLED=false
            учётной записи нет, пользователь служебный */}
        {authEnabled && (
          <button
            type="button"
            onClick={handleLogout}
            title="Выйти из системы"
            className="mt-2 flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm text-afm-200 transition-colors hover:bg-white/10 hover:text-white"
          >
            <svg viewBox="0 0 24 24" fill="currentColor" className="h-5 w-5 shrink-0">
              <path d="M16 13v-2H7V8l-5 4 5 4v-3h9zM20 3h-8v2h8v14h-8v2h8a2 2 0 002-2V5a2 2 0 00-2-2z" />
            </svg>
            {!collapsed && <span>Выйти</span>}
          </button>
        )}
      </div>
    </aside>
  )
}
