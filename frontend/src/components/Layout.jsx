import { Link, NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'

function NavItem({ to, children }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        `rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
          isActive ? 'bg-white/15 text-white' : 'text-afm-100 hover:bg-white/10 hover:text-white'
        }`
      }
    >
      {children}
    </NavLink>
  )
}

export default function Layout({ children }) {
  const { user, isAdministrator, logout } = useAuth()
  const navigate = useNavigate()

  const handleLogout = () => {
    logout()
    navigate('/login', { replace: true })
  }

  return (
    <div className="flex min-h-full flex-col">
      <header className="bg-afm-700 shadow">
        <div className="mx-auto flex max-w-[1600px] items-center gap-6 px-6 py-3">
          <Link to="/" className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded bg-white/15 text-lg font-bold text-white">
              БС
            </div>
            <div className="leading-tight">
              <div className="text-sm font-semibold text-white">Реестр БС</div>
              <div className="text-[11px] text-afm-200">
                Агентство по финансовому мониторингу РК
              </div>
            </div>
          </Link>

          <nav className="flex items-center gap-1">
            <NavItem to="/search">Поиск</NavItem>
            {isAdministrator && <NavItem to="/algorithms">Алгоритмы</NavItem>}
            {isAdministrator && <NavItem to="/settings">Настройки</NavItem>}
          </nav>

          <div className="ml-auto flex items-center gap-4">
            <div className="text-right leading-tight">
              <div className="text-sm font-medium text-white">{user?.username}</div>
              <div className="text-[11px] text-afm-200">
                {user?.role === 'administrator' ? 'Администратор' : 'Пользователь'}
              </div>
            </div>
            <button
              type="button"
              onClick={handleLogout}
              className="rounded-md border border-white/25 px-3 py-1.5 text-sm text-white transition-colors hover:bg-white/10"
            >
              Выйти
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-[1600px] flex-1 px-6 py-6">{children}</main>

      <footer className="border-t border-slate-200 bg-white py-3">
        <div className="mx-auto max-w-[1600px] px-6 text-xs text-slate-400">
          Реестр БС · закрытый контур · данные ограниченного доступа
        </div>
      </footer>
    </div>
  )
}
