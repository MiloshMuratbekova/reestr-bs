import axios from 'axios'

const TOKEN_KEY = 'reestr_bs_token'
const USER_KEY = 'reestr_bs_user'

export const tokenStorage = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (token) => localStorage.setItem(TOKEN_KEY, token),
  clear: () => {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
  },
  getUser: () => {
    const raw = localStorage.getItem(USER_KEY)
    try {
      return raw ? JSON.parse(raw) : null
    } catch {
      return null
    }
  },
  setUser: (user) => localStorage.setItem(USER_KEY, JSON.stringify(user)),
}

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || '/api',
  timeout: 600000, // тяжёлые запросы к ClickHouse и Qwen выполняются долго
})

api.interceptors.request.use((config) => {
  const token = tokenStorage.get()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      tokenStorage.clear()
      if (!window.location.pathname.startsWith('/login')) {
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  },
)

/** Приводит ошибку axios к понятному пользователю сообщению на русском языке. */
export function errorMessage(error, fallback = 'Не удалось выполнить операцию') {
  if (!error) return fallback

  if (error.code === 'ECONNABORTED') {
    return 'Превышено время ожидания ответа сервера. Запрос слишком тяжёлый — повторите позже.'
  }
  if (error.message === 'Network Error') {
    return 'Нет связи с сервером системы. Проверьте подключение к внутренней сети.'
  }

  const data = error.response?.data
  if (typeof data?.detail === 'string') return data.detail
  if (Array.isArray(data?.detail) && data.detail.length) {
    return data.detail.map((d) => d.msg || String(d)).join('; ')
  }
  if (typeof data?.error === 'string') return data.error

  const status = error.response?.status
  if (status === 403) return 'Недостаточно прав для выполнения этого действия.'
  if (status === 404) return 'Данные не найдены.'
  if (status === 503) return 'Смежный сервис временно недоступен.'

  return fallback
}

// --- Авторизация -----------------------------------------------------------
export const authApi = {
  // Спрашивается до входа: если сервер отвечает, что вход отключён,
  // страница логина не показывается вовсе
  mode: () => api.get('/auth/mode'),
  login: (username, password) => api.post('/auth/login', { username, password }),
  me: () => api.get('/auth/me'),
  changePassword: (currentPassword, newPassword) =>
    api.post('/auth/change-password', {
      current_password: currentPassword,
      new_password: newPassword,
    }),
  listUsers: () => api.get('/auth/users'),
  createUser: (payload) => api.post('/auth/users', payload),
  updateUser: (username, payload) =>
    api.patch(`/auth/users/${encodeURIComponent(username)}`, payload),
  deleteUser: (username) => api.delete(`/auth/users/${encodeURIComponent(username)}`),
}

// --- Реестр ----------------------------------------------------------------
export const registryApi = {
  search: (params) => api.get('/search', { params }),
  company: (bin) => api.get(`/company/${encodeURIComponent(bin)}`),
  explain: (bin, benefeciaryIinBin = null) =>
    api.post(`/company/${encodeURIComponent(bin)}/explain`, {
      benefeciary_iin_bin: benefeciaryIinBin,
    }),
  chat: (bin, message) => api.post('/chat', { bin, message }),
  stats: () => api.get('/stats'),
  health: () => api.get('/health'),
}

// --- Списки: ЮЛ, бенефициары, структуры владения, источники ----------------
export const listingApi = {
  companies: (params) => api.get('/companies', { params }),
  beneficiaries: (params) => api.get('/beneficiaries', { params }),
  beneficiary: (key) => api.get('/beneficiary', { params: { key } }),
  ownership: (id) => api.get(`/ownership/${encodeURIComponent(id)}`),
  sources: () => api.get('/sources'),
}

// --- Отчёты ----------------------------------------------------------------
export const reportsApi = {
  templates: () => api.get('/reports/templates'),
  history: (limit = 30) => api.get('/reports', { params: { limit } }),
  generate: (template, fileFormat, parameters = {}) =>
    api.post('/reports/generate', {
      template,
      file_format: fileFormat,
      parameters,
    }),
  remove: (id) => api.delete(`/reports/${id}`),
  // Файл забирается запросом с токеном, а не обычной ссылкой:
  // при включённом входе браузер не приложит заголовок Authorization
  download: (id) => api.get(`/reports/${id}/download`, { responseType: 'blob' }),
}

// --- Расписание ночного пересчёта ------------------------------------------
export const scheduleApi = {
  get: () => api.get('/schedule'),
  save: (payload) => api.post('/schedule', payload),
  runs: (limit = 20) => api.get('/schedule/runs', { params: { limit } }),
  runNow: () => api.post('/schedule/run'),
}

/** Сохраняет полученный файл на диск пользователя. */
export function saveBlob(blob, fileName) {
  const url = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = fileName
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.URL.revokeObjectURL(url)
}

// --- Настройки подключений и лимитов ---------------------------------------
export const settingsApi = {
  get: () => api.get('/settings'),
  save: (values) => api.post('/settings', { values }),
  testClickHouse: (payload = {}) => api.post('/ch/test', payload),
  testPostgres: (payload = {}) => api.post('/db/test', payload),
  testLlm: () => api.post('/llm/test'),
  models: () => api.get('/llm/models'),
}

// --- Алгоритмы -------------------------------------------------------------
export const algorithmsApi = {
  list: () => api.get('/algorithms'),
  get: (code) => api.get(`/algorithms/${encodeURIComponent(code)}`),
  create: (payload) => api.post('/algorithms', payload),
  update: (code, payload) => api.put(`/algorithms/${encodeURIComponent(code)}`, payload),
  run: (code) => api.post(`/algorithms/${encodeURIComponent(code)}/run`),
  aiUpdate: (code, requirement) =>
    api.post(`/algorithms/${encodeURIComponent(code)}/ai-update`, { requirement }),
  history: (code) => api.get(`/algorithms/${encodeURIComponent(code)}/history`),
  rollback: (code, historyId) =>
    api.post(`/algorithms/${encodeURIComponent(code)}/rollback/${historyId}`),
  recalculate: () => api.post('/recalculate'),
}

export default api
