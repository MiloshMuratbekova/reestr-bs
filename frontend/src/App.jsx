import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout.jsx'
import { Loading } from './components/ui.jsx'
import { useAuth } from './context/AuthContext.jsx'
import AlgorithmsPage from './pages/AlgorithmsPage.jsx'
import CompanyPage from './pages/CompanyPage.jsx'
import LoginPage from './pages/LoginPage.jsx'
import SearchPage from './pages/SearchPage.jsx'
import SettingsPage from './pages/SettingsPage.jsx'
import UsersPage from './pages/UsersPage.jsx'

function Protected({ children, adminOnly = false }) {
  const { isAuthenticated, isAdministrator, loading } = useAuth()

  if (loading) return <Loading text="Проверка сессии…" />
  if (!isAuthenticated) return <Navigate to="/login" replace />
  if (adminOnly && !isAdministrator) return <Navigate to="/search" replace />

  return <Layout>{children}</Layout>
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/search"
        element={
          <Protected>
            <SearchPage />
          </Protected>
        }
      />
      <Route
        path="/company/:bin"
        element={
          <Protected>
            <CompanyPage />
          </Protected>
        }
      />
      <Route
        path="/algorithms"
        element={
          <Protected adminOnly>
            <AlgorithmsPage />
          </Protected>
        }
      />
      <Route
        path="/users"
        element={
          <Protected adminOnly>
            <UsersPage />
          </Protected>
        }
      />
      <Route
        path="/settings"
        element={
          <Protected adminOnly>
            <SettingsPage />
          </Protected>
        }
      />
      <Route path="/" element={<Navigate to="/search" replace />} />
      <Route path="*" element={<Navigate to="/search" replace />} />
    </Routes>
  )
}
