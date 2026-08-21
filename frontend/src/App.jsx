import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout.jsx'
import { Loading } from './components/ui.jsx'
import { useAuth } from './context/AuthContext.jsx'
import BeneficiariesPage from './pages/BeneficiariesPage.jsx'
import CompaniesPage from './pages/CompaniesPage.jsx'
import CompanyPage from './pages/CompanyPage.jsx'
import DashboardPage from './pages/DashboardPage.jsx'
import LoginPage from './pages/LoginPage.jsx'
import OwnershipPage from './pages/OwnershipPage.jsx'
import ReportsPage from './pages/ReportsPage.jsx'
import SearchPage from './pages/SearchPage.jsx'
import SettingsHubPage from './pages/SettingsHubPage.jsx'
import SourcesPage from './pages/SourcesPage.jsx'

function Protected({ children, adminOnly = false }) {
  const { isAuthenticated, isAdministrator, loading } = useAuth()

  if (loading) return <Loading text="Проверка сессии…" />
  if (!isAuthenticated) return <Navigate to="/login" replace />

  // Раздел администратора: показываем причину, а не молча уводим на другую
  // страницу — иначе по ссылке из письма человек попадает не туда и не
  // понимает, почему
  if (adminOnly && !isAdministrator) {
    return (
      <Layout>
        <div className="card mx-auto max-w-lg p-8 text-center">
          <div className="text-3xl" aria-hidden="true">
            🔒
          </div>
          <h1 className="mt-3 text-base font-semibold text-slate-800">Недостаточно прав</h1>
          <p className="mt-2 text-sm text-slate-500">
            Этот раздел доступен только администратору системы. Обратитесь к администратору
            «Реестра БС», если доступ вам необходим.
          </p>
        </div>
      </Layout>
    )
  }

  return <Layout>{children}</Layout>
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      <Route
        path="/dashboard"
        element={
          <Protected>
            <DashboardPage />
          </Protected>
        }
      />
      <Route
        path="/search"
        element={
          <Protected>
            <SearchPage />
          </Protected>
        }
      />
      <Route
        path="/companies"
        element={
          <Protected>
            <CompaniesPage />
          </Protected>
        }
      />
      <Route
        path="/beneficiaries"
        element={
          <Protected>
            <BeneficiariesPage />
          </Protected>
        }
      />
      <Route
        path="/ownership"
        element={
          <Protected>
            <OwnershipPage />
          </Protected>
        }
      />
      <Route
        path="/ownership/:nodeId"
        element={
          <Protected>
            <OwnershipPage />
          </Protected>
        }
      />
      <Route
        path="/sources"
        element={
          <Protected>
            <SourcesPage />
          </Protected>
        }
      />
      <Route
        path="/reports"
        element={
          <Protected>
            <ReportsPage />
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

      {/* Алгоритмы, пользователи и расписание живут во вкладках настроек;
          прежние адреса сохранены, чтобы не ломать закладки */}
      <Route
        path="/settings"
        element={
          <Protected adminOnly>
            <SettingsHubPage />
          </Protected>
        }
      />
      <Route path="/algorithms" element={<Navigate to="/settings?tab=algorithms" replace />} />
      <Route path="/users" element={<Navigate to="/settings?tab=users" replace />} />
      <Route path="/schedule" element={<Navigate to="/settings?tab=schedule" replace />} />

      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  )
}
