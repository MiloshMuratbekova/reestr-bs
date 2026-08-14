import { useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { ErrorMessage, Spinner } from '../components/ui.jsx'
import { useAuth } from '../context/AuthContext.jsx'

export default function LoginPage() {
  const { login, isAuthenticated, loading } = useAuth()
  const navigate = useNavigate()

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  if (!loading && isAuthenticated) {
    return <Navigate to="/search" replace />
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    setError('')
    setSubmitting(true)
    const result = await login(username.trim(), password)
    setSubmitting(false)

    if (result.ok) {
      navigate('/search', { replace: true })
    } else {
      setError(result.message)
    }
  }

  return (
    <div className="flex min-h-full items-center justify-center bg-afm-800 px-4 py-12">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-lg bg-white/15 text-xl font-bold text-white">
            БС
          </div>
          <h1 className="text-xl font-semibold text-white">Реестр БС</h1>
          <p className="mt-1 text-sm text-afm-200">
            Агентство по финансовому мониторингу Республики Казахстан
          </p>
        </div>

        <form onSubmit={handleSubmit} className="card p-6">
          <h2 className="mb-5 text-base font-semibold text-slate-800">Вход в систему</h2>

          <div className="space-y-4">
            <div>
              <label className="label" htmlFor="username">
                Логин
              </label>
              <input
                id="username"
                className="input"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                autoFocus
                required
              />
            </div>

            <div>
              <label className="label" htmlFor="password">
                Пароль
              </label>
              <input
                id="password"
                type="password"
                className="input"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                required
              />
            </div>

            {error && <ErrorMessage message={error} />}

            <button type="submit" className="btn-primary w-full" disabled={submitting}>
              {submitting && <Spinner className="h-4 w-4" />}
              {submitting ? 'Выполняется вход…' : 'Войти'}
            </button>
          </div>
        </form>

        <p className="mt-6 text-center text-xs text-afm-300">
          Система содержит сведения ограниченного доступа
        </p>
      </div>
    </div>
  )
}
