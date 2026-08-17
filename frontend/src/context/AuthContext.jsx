import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { authApi, errorMessage, tokenStorage } from '../api/client.js'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => tokenStorage.getUser())
  // Ждём ответа /auth/mode всегда, даже когда токена нет: иначе интерфейс
  // успел бы отправить на страницу входа до того, как выяснится, что вход
  // отключён, и она бы мелькала при каждой загрузке
  const [loading, setLoading] = useState(true)
  // По умолчанию считаем, что вход нужен: если /auth/mode не ответит,
  // безопаснее показать логин, чем открыть систему всем
  const [authEnabled, setAuthEnabled] = useState(true)

  // Сначала выясняем у сервера, нужен ли вход вообще. Если он отключён
  // (AUTH_ENABLED=false), логин не показывается и пользователь считается
  // вошедшим — иначе интерфейс требовал бы пароль, которого сервер уже
  // не спрашивает. Только если вход нужен — проверяем сохранённый токен:
  // он мог истечь между сессиями.
  useEffect(() => {
    let cancelled = false

    authApi
      .mode()
      .then(({ data }) => {
        if (cancelled) return null
        if (data?.auth_enabled === false) {
          const guest = { username: 'служебный доступ', role: 'administrator' }
          setAuthEnabled(false)
          setUser(guest)
          setLoading(false)
          return null
        }
        setAuthEnabled(true)
        if (!tokenStorage.get()) {
          setLoading(false)
          return null
        }
        return authApi
          .me()
          .then(({ data: profile }) => {
            if (cancelled) return
            setUser(profile)
            tokenStorage.setUser(profile)
          })
          .catch(() => {
            if (cancelled) return
            tokenStorage.clear()
            setUser(null)
          })
          .finally(() => {
            if (!cancelled) setLoading(false)
          })
      })
      // Сервер недоступен или старой версии без /auth/mode — ведём себя
      // как раньше: считаем, что вход нужен
      .catch(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [])

  const login = useCallback(async (username, password) => {
    try {
      const { data } = await authApi.login(username, password)
      tokenStorage.set(data.access_token)
      const profile = { username: data.username, role: data.role }
      tokenStorage.setUser(profile)
      setUser(profile)
      return { ok: true }
    } catch (error) {
      return { ok: false, message: errorMessage(error, 'Не удалось войти в систему') }
    }
  }, [])

  const logout = useCallback(() => {
    tokenStorage.clear()
    setUser(null)
  }, [])

  const value = useMemo(
    () => ({
      user,
      loading,
      login,
      logout,
      isAuthenticated: Boolean(user),
      isAdministrator: user?.role === 'administrator',
      // Нужен интерфейсу, чтобы не показывать то, что при отключённом входе
      // работать не может: смену пароля и управление учётными записями.
      // Текущий пользователь тогда служебный, в базе его нет.
      authEnabled,
    }),
    [user, loading, login, logout, authEnabled],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth должен использоваться внутри AuthProvider')
  }
  return context
}
