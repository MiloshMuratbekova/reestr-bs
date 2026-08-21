import { useState } from 'react'
import { useAuth } from '../context/AuthContext.jsx'
import ChangePasswordDialog from './ChangePasswordDialog.jsx'
import Sidebar from './Sidebar.jsx'

/**
 * Каркас страницы: тёмная боковая панель слева, светлый контент справа.
 * Кнопка смены пароля вынесена в верхнюю полосу контента — в свёрнутой
 * панели ей не хватает места, а прятать её от пользователя нельзя.
 */
export default function Layout({ children }) {
  const { authEnabled } = useAuth()
  const [changingPassword, setChangingPassword] = useState(false)

  return (
    <div className="flex h-full">
      <Sidebar />

      <div className="flex min-w-0 flex-1 flex-col">
        {authEnabled && (
          <div className="flex justify-end border-b border-slate-200 bg-white px-6 py-2">
            <button
              type="button"
              onClick={() => setChangingPassword(true)}
              className="text-sm text-slate-500 transition-colors hover:text-afm-600"
            >
              Сменить пароль
            </button>
          </div>
        )}

        <main className="flex-1 overflow-y-auto px-6 py-6">
          <div className="mx-auto w-full max-w-[1600px]">{children}</div>
        </main>

        <footer className="border-t border-slate-200 bg-white py-3">
          <div className="mx-auto max-w-[1600px] px-6 text-xs text-slate-400">
            Реестр БС · закрытый контур · данные ограниченного доступа
          </div>
        </footer>
      </div>

      <ChangePasswordDialog
        open={changingPassword}
        onClose={() => setChangingPassword(false)}
      />
    </div>
  )
}
