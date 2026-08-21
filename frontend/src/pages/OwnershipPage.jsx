import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { errorMessage, listingApi, registryApi } from '../api/client.js'
import {
  EmptyState,
  ErrorMessage,
  InfoMessage,
  Loading,
  PageHeader,
  Spinner,
  value,
} from '../components/ui.jsx'

const WIDTH = 1000
const HEIGHT = 640
const CENTER = { x: WIDTH / 2, y: HEIGHT / 2 }
const RING = [0, 210, 380]

const EDGE_STYLE = {
  founder: { stroke: '#2b64a8', label: 'учредитель' },
  director: { stroke: '#7c3aed', label: 'руководитель' },
  beneficiary: { stroke: '#dc2626', label: 'бенефициар' },
}

/**
 * Раскладка графа: корень в центре, остальные узлы кольцами по расстоянию
 * от него. Расстояние считается по неориентированным связям — направление
 * важно для подписи ребра, но не для того, насколько узел далёк от корня.
 */
function layout(nodes, edges, rootId) {
  const neighbours = new Map()
  nodes.forEach((node) => neighbours.set(node.id, []))
  edges.forEach((edge) => {
    neighbours.get(edge.source)?.push(edge.target)
    neighbours.get(edge.target)?.push(edge.source)
  })

  const level = new Map([[rootId, 0]])
  const queue = [rootId]
  while (queue.length) {
    const current = queue.shift()
    for (const next of neighbours.get(current) || []) {
      if (!level.has(next)) {
        level.set(next, Math.min(2, level.get(current) + 1))
        queue.push(next)
      }
    }
  }

  const byLevel = new Map()
  nodes.forEach((node) => {
    const depth = level.has(node.id) ? level.get(node.id) : 2
    if (!byLevel.has(depth)) byLevel.set(depth, [])
    byLevel.get(depth).push(node)
  })

  const positions = new Map()
  byLevel.forEach((group, depth) => {
    if (depth === 0) {
      group.forEach((node) => positions.set(node.id, { ...CENTER }))
      return
    }
    const radius = RING[depth] || RING[2]
    group.forEach((node, index) => {
      // Небольшой сдвиг начального угла, чтобы кольца не выстраивались
      // в одну линию и подписи не наезжали друг на друга
      const angle = (2 * Math.PI * index) / group.length - Math.PI / 2 + depth * 0.35
      positions.set(node.id, {
        x: CENTER.x + radius * Math.cos(angle),
        y: CENTER.y + radius * Math.sin(angle) * 0.72,
      })
    })
  })

  return positions
}

function GraphNode({ node, position, onOpen, isRoot }) {
  const isCompany = node.kind === 'company'
  const label = value(node.name)
  const short = label.length > 26 ? `${label.slice(0, 25)}…` : label

  return (
    <g
      transform={`translate(${position.x}, ${position.y})`}
      onClick={() => !isRoot && onOpen(node.id)}
      style={{ cursor: isRoot ? 'default' : 'pointer' }}
    >
      <title>{`${label}\n${node.id}\n${isCompany ? 'юридическое лицо' : 'физическое лицо'}`}</title>

      {isCompany ? (
        <rect
          x={-84}
          y={-24}
          width={168}
          height={48}
          rx={6}
          fill={isRoot ? '#1f4d87' : '#ffffff'}
          stroke={node.is_state_owned ? '#64748b' : '#1f4d87'}
          strokeWidth={isRoot ? 2.5 : 1.5}
        />
      ) : (
        <circle
          r={38}
          fill={isRoot ? '#1f4d87' : '#ffffff'}
          stroke="#7c3aed"
          strokeWidth={isRoot ? 2.5 : 1.5}
        />
      )}

      <text
        textAnchor="middle"
        y={isCompany ? -2 : -4}
        style={{ fontSize: 11, fontWeight: 600 }}
        fill={isRoot ? '#ffffff' : '#1e293b'}
      >
        {short}
      </text>
      <text
        textAnchor="middle"
        y={isCompany ? 13 : 11}
        style={{ fontSize: 9, fontFamily: 'monospace' }}
        fill={isRoot ? '#cbd5e1' : '#64748b'}
      >
        {node.id.length > 22 ? `${node.id.slice(0, 21)}…` : node.id}
      </text>
    </g>
  )
}

export default function OwnershipPage() {
  const navigate = useNavigate()
  const { nodeId } = useParams()

  const [queryText, setQueryText] = useState('')
  const [suggestions, setSuggestions] = useState([])
  const [searching, setSearching] = useState(false)

  const [graph, setGraph] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const [zoom, setZoom] = useState(1)
  const [pan, setPan] = useState({ x: 0, y: 0 })

  const load = useCallback((id) => {
    if (!id) return
    setLoading(true)
    setError('')
    listingApi
      .ownership(id)
      .then(({ data }) => {
        setGraph(data)
        setZoom(1)
        setPan({ x: 0, y: 0 })
      })
      .catch((err) => {
        setError(errorMessage(err, 'Структура владения не построена'))
        setGraph(null)
      })
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (nodeId) load(nodeId)
  }, [nodeId, load])

  const runSearch = async (event) => {
    event.preventDefault()
    const text = queryText.trim()
    if (text.length < 2) {
      setError('Введите не менее двух символов')
      return
    }

    // Строка из одних цифр — это готовый идентификатор, открываем сразу
    if (/^\d{6,20}$/.test(text)) {
      navigate(`/ownership/${encodeURIComponent(text)}`)
      return
    }

    setSearching(true)
    setError('')
    try {
      const { data } = await registryApi.search({ query: text, limit: 20 })
      setSuggestions(data)
      if (data.length === 0) {
        setError('Компании с таким наименованием не найдены')
      }
    } catch (err) {
      setError(errorMessage(err, 'Поиск не выполнен'))
    } finally {
      setSearching(false)
    }
  }

  const positions = useMemo(() => {
    if (!graph?.nodes?.length) return new Map()
    return layout(graph.nodes, graph.edges || [], graph.root?.id)
  }, [graph])

  const openNode = (id) => navigate(`/ownership/${encodeURIComponent(id)}`)

  return (
    <div className="space-y-4">
      <PageHeader
        title="Структуры владения"
        description="Учредители, руководители и бенефициары вокруг выбранного лица"
      />

      <form onSubmit={runSearch} className="card p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <div className="flex-1">
            <label className="label" htmlFor="ownership-query">
              БИН компании, ИИН физического лица или наименование
            </label>
            <input
              id="ownership-query"
              className="input"
              value={queryText}
              onChange={(event) => setQueryText(event.target.value)}
              placeholder="Например: 123456789012 или ТОО «Ромашка»"
            />
          </div>
          <button type="submit" className="btn-primary sm:w-36" disabled={searching}>
            {searching && <Spinner className="h-4 w-4" />}
            {searching ? 'Поиск…' : 'Построить'}
          </button>
        </div>
      </form>

      {suggestions.length > 0 && (
        <div className="card p-4">
          <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
            Выберите компанию
          </div>
          <div className="flex flex-wrap gap-2">
            {suggestions.map((item) => (
              <button
                key={item.taxpayer_iin_bin}
                type="button"
                className="rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50"
                onClick={() => {
                  setSuggestions([])
                  openNode(item.taxpayer_iin_bin)
                }}
              >
                {value(item.taxpayer_name)}
                <span className="ml-2 font-mono text-xs text-slate-400">
                  {item.taxpayer_iin_bin}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}

      {error && <ErrorMessage message={error} />}

      {loading && <Loading text="Построение структуры владения…" />}

      {!loading && !graph && !nodeId && (
        <EmptyState
          title="Структура не выбрана"
          description="Введите БИН, ИИН или наименование — граф построится вокруг найденного лица"
        />
      )}

      {!loading && graph?.root && (
        <div className="card">
          <div className="card-header">
            <div className="min-w-0">
              <span className="card-title">{value(graph.root.name)}</span>
              <span className="ml-2 font-mono text-xs text-slate-400">{graph.root.id}</span>
            </div>
            <div className="flex items-center gap-1">
              <button
                type="button"
                className="rounded border border-slate-300 px-2 py-1 text-sm"
                onClick={() => setZoom((z) => Math.min(3, z * 1.25))}
                title="Приблизить"
              >
                +
              </button>
              <button
                type="button"
                className="rounded border border-slate-300 px-2 py-1 text-sm"
                onClick={() => setZoom((z) => Math.max(0.4, z / 1.25))}
                title="Отдалить"
              >
                −
              </button>
              <button
                type="button"
                className="rounded border border-slate-300 px-2 py-1 text-sm"
                onClick={() => {
                  setZoom(1)
                  setPan({ x: 0, y: 0 })
                }}
                title="Сбросить масштаб"
              >
                Сброс
              </button>
              {graph.root.kind === 'company' && (
                <button
                  type="button"
                  className="ml-2 rounded border border-slate-300 px-2 py-1 text-sm"
                  onClick={() => navigate(`/company/${encodeURIComponent(graph.root.id)}`)}
                >
                  Карточка
                </button>
              )}
            </div>
          </div>

          {graph.edges.length === 0 ? (
            <EmptyState
              title="Связи не найдены"
              description="По этому лицу нет ни учредителей, ни руководителей, ни бенефициаров"
            />
          ) : (
            <>
              <div className="overflow-hidden bg-slate-50">
                <svg
                  viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
                  className="w-full"
                  style={{ height: HEIGHT }}
                  onMouseDown={(event) => {
                    const startX = event.clientX
                    const startY = event.clientY
                    const origin = { ...pan }
                    const move = (moveEvent) => {
                      setPan({
                        x: origin.x + (moveEvent.clientX - startX),
                        y: origin.y + (moveEvent.clientY - startY),
                      })
                    }
                    const up = () => {
                      window.removeEventListener('mousemove', move)
                      window.removeEventListener('mouseup', up)
                    }
                    window.addEventListener('mousemove', move)
                    window.addEventListener('mouseup', up)
                  }}
                >
                  <g
                    transform={`translate(${pan.x + CENTER.x}, ${pan.y + CENTER.y}) scale(${zoom}) translate(${-CENTER.x}, ${-CENTER.y})`}
                  >
                    {graph.edges.map((edge, index) => {
                      const from = positions.get(edge.source)
                      const to = positions.get(edge.target)
                      if (!from || !to) return null
                      const style = EDGE_STYLE[edge.kind] || EDGE_STYLE.founder
                      const midX = (from.x + to.x) / 2
                      const midY = (from.y + to.y) / 2
                      const caption = [edge.share, edge.ball3 != null ? `${edge.ball3}%` : '']
                        .filter(Boolean)
                        .join(' · ')
                      return (
                        <g key={`${edge.source}-${edge.target}-${edge.kind}-${index}`}>
                          <line
                            x1={from.x}
                            y1={from.y}
                            x2={to.x}
                            y2={to.y}
                            stroke={style.stroke}
                            strokeWidth={1.4}
                            strokeOpacity={0.55}
                            strokeDasharray={edge.kind === 'director' ? '5 3' : undefined}
                          />
                          {caption && (
                            <text
                              x={midX}
                              y={midY - 4}
                              textAnchor="middle"
                              style={{ fontSize: 9 }}
                              fill={style.stroke}
                            >
                              {caption}
                            </text>
                          )}
                        </g>
                      )
                    })}

                    {graph.nodes.map((node) => {
                      const position = positions.get(node.id)
                      if (!position) return null
                      return (
                        <GraphNode
                          key={node.id}
                          node={node}
                          position={position}
                          onOpen={openNode}
                          isRoot={node.id === graph.root.id}
                        />
                      )
                    })}
                  </g>
                </svg>
              </div>

              <div className="flex flex-wrap items-center gap-5 border-t border-slate-200 px-5 py-3 text-xs text-slate-500">
                <span className="flex items-center gap-2">
                  <span className="inline-block h-3 w-5 rounded-sm border border-afm-600" />
                  юридическое лицо
                </span>
                <span className="flex items-center gap-2">
                  <span className="inline-block h-4 w-4 rounded-full border border-violet-600" />
                  физическое лицо
                </span>
                {Object.entries(EDGE_STYLE).map(([kind, style]) => (
                  <span key={kind} className="flex items-center gap-2">
                    <span
                      className="inline-block h-0.5 w-6"
                      style={{ backgroundColor: style.stroke }}
                    />
                    {style.label}
                  </span>
                ))}
                <span className="ml-auto">
                  Клик по узлу перестраивает граф вокруг него · панель тянется мышью
                </span>
              </div>
            </>
          )}
        </div>
      )}

      {!loading && graph?.root?.kind === 'company' && graph.nodes.length === 1 && (
        <InfoMessage tone="warning">
          У компании не найдено ни учредителей, ни руководителей, ни бенефициаров. Возможно,
          алгоритмы ещё не рассчитаны либо данные по ней отсутствуют в справочниках.
        </InfoMessage>
      )}
    </div>
  )
}
