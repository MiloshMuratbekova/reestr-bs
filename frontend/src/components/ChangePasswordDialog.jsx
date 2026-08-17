import { useState } from 'react'
import { authApi, errorMessage } from '../api/client.js'
import Modal from './Modal.jsx'
import { ErrorMessage, InfoMessage, Spinner } from './ui.jsx'

/** Смена собственного пароля. Доступна любому вошедшему, включая роль «Пользователь». */
export default function ChangePasswordDialog({ open, onClose }) {
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [repeat, setRepeat] = useState('')
  const [error, setError] = useState('')
  const [done, setDone] = useState(false)
  const [saving, setSaving] = useState(false)

  const close = () => {
    setCurrent('')
    setNext('')
    setRepeat('')
    setError('')
    setDone(false)
    onClose()
  }

  const save = async () => {
    if (next !== repeat) {
      setError('Новый пароль и подтверждение не совпадают')
      return
    }
    setSaving(true)
    setError('')
    try {
      await authApi.changePassword(current, next)
      setDone(true)
    } catch (err) {
      setError(errorMessage(err, 'Не удалось сменить пароль'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      open={open}
      title="Смена пароля"
      onClose={close}
      size="md"
      footer={
        done ? (
          <button type="button" className="btn-primary" onClick={close}>
            Закрыть
          </button>
        ) : (
          <>
            <button type="button" className="btn-secondary" onClick={close}>
              Отмена
            </button>
            <button
              type="button"
              className="btn-primary"
              onClick={save}
              disabled={saving || !current || next.length < 6}
            >
              {saving && <Spinner className="h-4 w-4" />}
              Сохранить
            </button>
          </>
        )
      }
    >
      {done ? (
        <InfoMessage tone="success">
          Пароль изменён. При следующем входе используйте новый.
        </InfoMessage>
      ) : (
        <div className="space-y-4">
          <div>
            <label className="label">Текущий пароль</label>
            <input
              type="password"
              className="input"
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
              autoComplete="current-password"
            />
          </div>
          <div>
            <label className="label">Новый пароль</label>
            <input
              type="password"
              className="input"
              value={next}
              onChange={(e) => setNext(e.target.value)}
              autoComplete="new-password"
            />
            <p className="mt-1 text-xs text-slate-500">Не короче шести символов</p>
          </div>
          <div>
            <label className="label">Повторите новый пароль</label>
            <input
              type="password"
              className="input"
              value={repeat}
              onChange={(e) => setRepeat(e.target.value)}
              autoComplete="new-password"
            />
          </div>
          {error && <ErrorMessage message={error} />}
        </div>
      )}
    </Modal>
  )
}
