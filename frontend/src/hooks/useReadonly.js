import { useEffect, useState } from 'react'
import { registryApi } from '../api/client.js'

/** Ответ /health кэшируется на всё приложение: признак за сеанс не меняется. */
let pending = null

/** Признак «база только на чтение».
 *
 * Учётная запись ClickHouse может не иметь прав на запись — тогда запуск
 * алгоритмов и пересчёт сервер отклонит. Чтобы не показывать кнопки,
 * которые заведомо не сработают, страницы спрашивают признак здесь.
 * При недоступном /health возвращается false: лучше показать кнопку и дать
 * серверу ответить понятной ошибкой, чем спрятать её из-за сбоя сети.
 */
export function useReadonly() {
  const [readonly, setReadonly] = useState(false)

  useEffect(() => {
    let alive = true
    if (!pending) {
      pending = registryApi
        .health()
        .then(({ data }) => Boolean(data?.readonly))
        .catch(() => false)
    }
    pending.then((flag) => {
      if (alive) setReadonly(flag)
    })
    return () => {
      alive = false
    }
  }, [])

  return readonly
}
