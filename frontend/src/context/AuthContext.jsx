import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { authApi, errorMessage, tokenStorage } from '../api/client.js'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => tokenStorage.getUser())
  const [loading, setLoading] = useState(Boolean(tokenStorage.get()))

  // Проверяем токен при загрузке — он мог истечь между сессиями
  useEffect(() => {
    if (!tokenStorage.get()) {
      setLoading(false)
      return
    }
    let cancelled = false
    authApi
      .me()
      .then(({ data }) => {
        if (cancelled) return
        setUser(data)
        tokenStorage.setUser(data)
      })
      .catch(() => {
        if (cancelled) return
        tokenStorage.clear()
        setUser(null)
      })
      .finally(() => {
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
    }),
    [user, loading, login, logout],
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
