import { useCallback, useEffect, useState } from 'react'
import { authApi, errorMessage } from '../api/client.js'
import Modal from '../components/Modal.jsx'
import { ErrorMessage, InfoMessage, Loading, Spinner, value } from '../components/ui.jsx'
import { useAuth } from '../context/AuthContext.jsx'

/**
 * Пользователи системы.
 *
 * Всё управление учётными записями делается здесь: создание, смена пароля,
 * роль, блокировка, удаление. Раньше пароль задавался только при первом
 * запуске и потом не менялся — приходилось править базу вручную.
 */

const ROLE_LABEL = { administrator: 'Администратор', user: 'Пользователь' }

function formatDate(raw) {
  if (!raw) return '—'
  const d = new Date(raw)
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleString('ru-RU')
}

export default function UsersPage() {
  const { user: me } = useAuth()

  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState('')

  const [creating, setCreating] = useState(false)
  const [form, setForm] = useState({ username: '', password: '', role: 'user', full_name: '' })

  const [editing, setEditing] = useState(null)
  const [newPassword, setNewPassword] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const { data } = await authApi.listUsers()
      setUsers(data)
    } catch (err) {
      setError(errorMessage(err, 'Не удалось загрузить список пользователей'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const run = async (key, action, successText) => {
    setBusy(key)
    setError('')
    setNotice('')
    try {
      await action()
      setNotice(successText)
      await load()
      return true
    } catch (err) {
      setError(errorMessage(err, 'Операция не выполнена'))
      return false
    } finally {
      setBusy('')
    }
  }

  const createUser = async () => {
    const ok = await run(
      '__create__',
      () => authApi.createUser(form),
      `Пользователь ${form.username} создан`,
    )
    if (ok) {
      setCreating(false)
      setForm({ username: '', password: '', role: 'user', full_name: '' })
    }
  }

  const savePassword = async () => {
    const ok = await run(
      editing.username,
      () => authApi.updateUser(editing.username, { password: newPassword }),
      `Пароль пользователя ${editing.username} изменён`,
    )
    if (ok) {
      setEditing(null)
      setNewPassword('')
    }
  }

  const toggleActive = (u) =>
    run(
      u.username,
      () => authApi.updateUser(u.username, { is_active: !u.is_active }),
      u.is_active ? `${u.username} заблокирован` : `${u.username} разблокирован`,
    )

  const changeRole = (u, role) =>
    run(u.username, () => authApi.updateUser(u.username, { role }), `Роль ${u.username} изменена`)

  const removeUser = (u) => {
    if (!window.confirm(`Удалить пользователя ${u.username}? Действие необратимо.`)) return
    run(u.username, () => authApi.deleteUser(u.username), `Пользователь ${u.username} удалён`)
  }

  if (loading) return <Loading text="Загрузка пользователей…" />

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-slate-800">Пользователи</h1>
          <p className="mt-0.5 text-sm text-slate-500">
            Создание учётных записей, смена паролей, роли и блокировка
          </p>
        </div>
        <button type="button" className="btn-primary" onClick={() => setCreating(true)}>
          Добавить пользователя
        </button>
      </div>

      {notice && <InfoMessage tone="success">{notice}</InfoMessage>}
      {error && <ErrorMessage message={error} />}

      <section className="card">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Логин</th>
                <th>ФИО</th>
                <th>Роль</th>
                <th>Состояние</th>
                <th>Последний вход</th>
                <th className="text-right">Действия</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => {
                const isMe = u.username === me?.username
                const working = busy === u.username
                return (
                  <tr key={u.username}>
                    <td className="font-medium text-slate-800">
                      {u.username}
                      {isMe && <span className="ml-2 text-xs text-slate-400">это вы</span>}
                    </td>
                    <td className="text-sm">{value(u.full_name)}</td>
                    <td>
                      <select
                        className="input py-1 text-xs"
                        value={u.role}
                        onChange={(e) => changeRole(u, e.target.value)}
                        disabled={working}
                      >
                        <option value="administrator">{ROLE_LABEL.administrator}</option>
                        <option value="user">{ROLE_LABEL.user}</option>
                      </select>
                    </td>
                    <td>
                      <span
                        className={`badge ${
                          u.is_active
                            ? 'bg-emerald-100 text-emerald-800'
                            : 'bg-slate-200 text-slate-600'
                        }`}
                      >
                        {u.is_active ? 'активен' : 'заблокирован'}
                      </span>
                    </td>
                    <td className="text-xs text-slate-500">{formatDate(u.last_login_at)}</td>
                    <td>
                      <div className="flex justify-end gap-1">
                        <button
                          type="button"
                          className="btn-secondary px-2 py-1 text-xs"
                          onClick={() => {
                            setEditing(u)
                            setNewPassword('')
                          }}
                          disabled={working}
                        >
                          {working ? <Spinner className="h-3 w-3" /> : 'Пароль'}
                        </button>
                        <button
                          type="button"
                          className="btn-secondary px-2 py-1 text-xs"
                          onClick={() => toggleActive(u)}
                          disabled={working || isMe}
                          title={isMe ? 'Нельзя заблокировать себя' : ''}
                        >
                          {u.is_active ? 'Заблокировать' : 'Разблокировать'}
                        </button>
                        <button
                          type="button"
                          className="btn-danger px-2 py-1 text-xs"
                          onClick={() => removeUser(u)}
                          disabled={working || isMe}
                          title={isMe ? 'Нельзя удалить себя' : ''}
                        >
                          Удалить
                        </button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </section>

      <InfoMessage>
        Последнего действующего администратора нельзя заблокировать, удалить или понизить в роли —
        иначе управлять системой станет некому и учётные записи придётся править прямо в базе.
      </InfoMessage>

      {/* --- создание --- */}
      <Modal
        open={creating}
        title="Новый пользователь"
        onClose={() => setCreating(false)}
        size="md"
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={() => setCreating(false)}>
              Отмена
            </button>
            <button
              type="button"
              className="btn-primary"
              onClick={createUser}
              disabled={
                busy === '__create__' || form.username.length < 3 || form.password.length < 6
              }
            >
              {busy === '__create__' && <Spinner className="h-4 w-4" />}
              Создать
            </button>
          </>
        }
      >
        <div className="space-y-4">
          <div>
            <label className="label">Логин</label>
            <input
              className="input"
              value={form.username}
              onChange={(e) => setForm({ ...form, username: e.target.value })}
              autoComplete="off"
            />
            <p className="mt-1 text-xs text-slate-500">Не короче трёх символов</p>
          </div>
          <div>
            <label className="label">Пароль</label>
            <input
              type="password"
              className="input"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              autoComplete="new-password"
            />
            <p className="mt-1 text-xs text-slate-500">Не короче шести символов</p>
          </div>
          <div>
            <label className="label">ФИО</label>
            <input
              className="input"
              value={form.full_name}
              onChange={(e) => setForm({ ...form, full_name: e.target.value })}
            />
          </div>
          <div>
            <label className="label">Роль</label>
            <select
              className="input"
              value={form.role}
              onChange={(e) => setForm({ ...form, role: e.target.value })}
            >
              <option value="user">Пользователь — просмотр данных и чат</option>
              <option value="administrator">
                Администратор — плюс алгоритмы, настройки и пользователи
              </option>
            </select>
          </div>
        </div>
      </Modal>

      {/* --- смена пароля другому --- */}
      <Modal
        open={Boolean(editing)}
        title={editing ? `Новый пароль: ${editing.username}` : ''}
        onClose={() => setEditing(null)}
        size="md"
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={() => setEditing(null)}>
              Отмена
            </button>
            <button
              type="button"
              className="btn-primary"
              onClick={savePassword}
              disabled={newPassword.length < 6 || busy === editing?.username}
            >
              {busy === editing?.username && <Spinner className="h-4 w-4" />}
              Сохранить
            </button>
          </>
        }
      >
        <div>
          <label className="label">Новый пароль</label>
          <input
            type="password"
            className="input"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            autoComplete="new-password"
          />
          <p className="mt-1 text-xs text-slate-500">
            Не короче шести символов. Прежний пароль знать не требуется — вы администратор.
          </p>
        </div>
      </Modal>
    </div>
  )
}
