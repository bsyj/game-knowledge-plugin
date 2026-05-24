import { useEffect, useState, useCallback } from "react"
import {
  Plus, Trash2, Search, RefreshCw, GitGraph, Link, X, Pencil,
} from "lucide-react"
import {
  fetchGraph, searchGraph, createGraphNode, deleteGraphNode,
  createGraphEdge, deleteGraphEdge, renameGraphNode,
} from "@/lib/api"
import { useToast } from "@/components/Toast"
import Card from "@/components/Card"
import Button from "@/components/Button"
import Loading from "@/components/Loading"
import { cn } from "@/lib/utils"

interface GraphNode { id?: string; name: string; type?: string; count?: number }
interface GraphEdge { hash?: string; subject: string; predicate: string; object: string; weight?: number; confidence?: number }

interface GraphApiPayload {
  success?: boolean
  graph?: { nodes?: unknown[]; edges?: unknown[] }
  nodes?: unknown[]
  edges?: unknown[]
  items?: unknown[]
}

type GraphSubTab = "overview" | "nodes" | "edges" | "search"

const SUB_TABS: { key: GraphSubTab; label: string }[] = [
  { key: "overview", label: "概览" },
  { key: "search", label: "搜索" },
  { key: "nodes", label: "节点" },
  { key: "edges", label: "关系" },
]

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" ? value as Record<string, unknown> : {}
}

function normalizeNode(value: unknown): GraphNode | null {
  const item = asRecord(value)
  const name = String(item.name ?? item.id ?? item.entity_name ?? item.title ?? "").trim()
  if (!name) return null
  return {
    id: String(item.id ?? name),
    name,
    type: item.type ? String(item.type) : undefined,
    count: typeof item.count === "number" ? item.count : Number(item.appearance_count ?? 0) || undefined,
  }
}

function normalizeEdge(value: unknown): GraphEdge | null {
  const item = asRecord(value)
  const subject = String(item.subject ?? item.source ?? "").trim()
  const object = String(item.object ?? item.target ?? "").trim()
  if (!subject || !object) return null
  return {
    hash: String(item.hash ?? item.relation_hash ?? ""),
    subject,
    predicate: String(item.predicate ?? item.label ?? "关联").trim() || "关联",
    object,
    weight: Number(item.weight ?? item.confidence ?? 0) || undefined,
    confidence: Number(item.confidence ?? item.weight ?? 0) || undefined,
  }
}

function normalizeGraphPayload(payload: unknown): { nodes: GraphNode[]; edges: GraphEdge[] } {
  const data = asRecord(payload) as GraphApiPayload
  const graph = asRecord(data.graph)
  const rawNodes = Array.isArray(graph.nodes) ? graph.nodes : Array.isArray(data.nodes) ? data.nodes : []
  const rawEdges = Array.isArray(graph.edges) ? graph.edges : Array.isArray(data.edges) ? data.edges : []
  const nodes = rawNodes.map(normalizeNode).filter((node): node is GraphNode => node !== null)
  const edges = rawEdges.map(normalizeEdge).filter((edge): edge is GraphEdge => edge !== null)
  return { nodes, edges }
}

function graphFromSearchPayload(payload: unknown): { nodes: GraphNode[]; edges: GraphEdge[] } {
  const data = asRecord(payload) as GraphApiPayload
  if (!Array.isArray(data.items)) return normalizeGraphPayload(payload)

  const nodeMap = new Map<string, GraphNode>()
  const edges: GraphEdge[] = []
  for (const raw of data.items) {
    const item = asRecord(raw)
    if (item.type === "relation") {
      const edge = normalizeEdge(item)
      if (edge) {
        edges.push(edge)
        nodeMap.set(edge.subject, { name: edge.subject })
        nodeMap.set(edge.object, { name: edge.object })
      }
    } else {
      const node = normalizeNode(item)
      if (node) nodeMap.set(node.name, node)
    }
  }
  return { nodes: Array.from(nodeMap.values()), edges }
}

function graphLayout(nodes: GraphNode[], edges: GraphEdge[]) {
  const visibleNodes = nodes.slice(0, 48)
  const nodeNames = new Set(visibleNodes.map((node) => node.name))
  const visibleEdges = edges.filter((edge) => nodeNames.has(edge.subject) && nodeNames.has(edge.object)).slice(0, 90)
  const centerX = 360
  const centerY = 185
  const radius = visibleNodes.length > 12 ? 145 : 112
  const positions = new Map<string, { x: number; y: number }>()
  visibleNodes.forEach((node, index) => {
    const angle = (index / Math.max(visibleNodes.length, 1)) * Math.PI * 2 - Math.PI / 2
    const ring = radius * (0.72 + (index % 3) * 0.14)
    positions.set(node.name, {
      x: centerX + Math.cos(angle) * ring,
      y: centerY + Math.sin(angle) * ring,
    })
  })
  return { visibleNodes, visibleEdges, positions }
}

export default function GraphPanel() {
  const { toast } = useToast()
  const [nodes, setNodes] = useState<GraphNode[]>([])
  const [edges, setEdges] = useState<GraphEdge[]>([])
  const [loading, setLoading] = useState(false)
  const [subTab, setSubTab] = useState<GraphSubTab>("overview")
  const [searchQ, setSearchQ] = useState("")

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = normalizeGraphPayload(await fetchGraph(500))
      setNodes(data.nodes)
      setEdges(data.edges)
    } catch { toast("加载图谱失败", "error") } finally { setLoading(false) }
  }, [toast])

  useEffect(() => { load() }, [load])

  const handleSearch = async () => {
    if (!searchQ.trim()) return
    setLoading(true)
    try {
      const data = graphFromSearchPayload(await searchGraph(searchQ.trim()))
      setNodes(data.nodes)
      setEdges(data.edges)
      setSubTab("overview")
      toast(`找到 ${data.nodes.length} 个节点、${data.edges.length} 条关系`, "info")
    } catch { toast("搜索失败", "error") } finally { setLoading(false) }
  }

  const handleDeleteNode = async (name: string) => {
    if (!window.confirm(`确定删除节点「${name}」吗？相关关系可能会受影响。`)) return
    try { await deleteGraphNode(name); toast("节点已删除", "success"); load() } catch { toast("删除失败", "error") }
  }

  const handleRenameNode = async (name: string) => {
    const nextName = window.prompt("输入新的节点名称", name)?.trim()
    if (!nextName || nextName === name) return
    try {
      await renameGraphNode(name, nextName)
      toast("节点已重命名", "success")
      load()
    } catch {
      toast("重命名失败", "error")
    }
  }

  const handleDeleteEdge = async (s: string, p: string, o: string) => {
    if (!window.confirm(`确定删除关系「${s} - ${p} - ${o}」吗？`)) return
    try { await deleteGraphEdge(s, p, o); toast("关系已删除", "success"); load() } catch { toast("删除失败", "error") }
  }

  return (
    <div className="space-y-5">
      {/* ═══ 子选项卡 ═══ */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="inline-flex rounded-full border border-white/10 bg-gradient-to-r from-default-100/50 via-content1/50 to-default-100/30 p-1.5 shadow-inner">
          {SUB_TABS.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setSubTab(tab.key)}
              className={cn(
                "rounded-full px-3.5 py-1.5 text-xs font-medium transition-colors",
                subTab === tab.key
                  ? "bg-gradient-to-r from-primary to-primary/80 text-primary-foreground shadow-sm"
                  : "text-default-500 hover:bg-content1/55 hover:text-default-900",
              )}
            >
              {tab.label}
            </button>
          ))}
        </div>
        <Button variant="outline" size="sm" onClick={load}><RefreshCw className="h-3 w-3" />刷新</Button>
      </div>

      {loading && <Loading />}

      {/* ═══ 统计概览 ═══ */}
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="flex items-center gap-3 rounded-xl border bg-default-100/30 p-4">
          <div className="flex-none rounded-xl bg-primary/10 p-2 text-primary">
            <GitGraph className="h-5 w-5" />
          </div>
          <div>
            <div className="text-2xl font-bold text-primary">{nodes.length}</div>
            <div className="text-xs text-default-500">节点</div>
          </div>
        </div>
        <div className="flex items-center gap-3 rounded-xl border bg-default-100/30 p-4">
          <div className="flex-none rounded-xl bg-chart-2/10 p-2 text-chart-2">
            <Link className="h-5 w-5" />
          </div>
          <div>
            <div className="text-2xl font-bold text-chart-2">{edges.length}</div>
            <div className="text-xs text-default-500">关系</div>
          </div>
        </div>
      </div>

      {subTab === "overview" && (nodes.length > 0 || edges.length > 0) && (
        <GraphCanvas nodes={nodes} edges={edges} />
      )}

      {/* ═══ 搜索 ═══ */}
      {subTab === "search" && (
        <Card title="搜索图谱">
          <div className="flex gap-2">
            <input type="text" value={searchQ} onChange={(e) => setSearchQ(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSearch()}
              placeholder="输入关键词搜索节点和关系…"
              className="h-9 flex-1 rounded-xl border border-white/10 bg-transparent px-3 text-sm text-default-900 placeholder:text-default-500 focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
            />
            <Button onClick={handleSearch}><Search className="h-4 w-4" />搜索</Button>
          </div>
        </Card>
      )}

      {/* ═══ 概览 / 节点列表 ═══ */}
      {(subTab === "overview" || subTab === "nodes") && nodes.length > 0 && (
        <Card title={`节点 (${nodes.length})`}>
          <div className="flex flex-wrap gap-1.5">
            {nodes.map((n) => (
              <span key={n.name} className="inline-flex items-center gap-1 rounded-full bg-accent/30 border border-accent/60 px-3 py-1 text-xs font-medium transition-opacity hover:opacity-80">
                <GitGraph className="h-3 w-3 text-accent-foreground/70" />
                {n.name}
                {n.type && <span className="text-default-500">· {n.type}</span>}
                <button onClick={() => handleRenameNode(n.name)} className="ml-1 text-default-500 hover:text-primary" title="重命名节点"><Pencil className="h-3 w-3" /></button>
                <button onClick={() => handleDeleteNode(n.name)} className="ml-1 text-default-500 hover:text-destructive" title="删除节点"><X className="h-3 w-3" /></button>
              </span>
            ))}
          </div>
        </Card>
      )}

      {/* ═══ 概览 / 关系列表 ═══ */}
      {(subTab === "overview" || subTab === "edges") && edges.length > 0 && (
        <Card title={`关系 (${edges.length})`}>
          <div className="space-y-1.5">
            {edges.map((e, i) => (
              <div key={i} className="flex flex-wrap items-center gap-2 rounded-xl border border-chart-2/20 bg-[hsl(142.1_40%_12%)] px-3 py-2 text-sm transition-opacity hover:opacity-80">
                <Link className="h-3.5 w-3.5 text-chart-2/60 flex-shrink-0" />
                <span className="font-semibold text-default-900">{e.subject}</span>
                <span className="rounded bg-chart-2/15 px-1.5 py-0.5 text-xs text-chart-2/80">{e.predicate}</span>
                <span className="font-semibold text-default-900">{e.object}</span>
                {e.weight != null && (
                  <span className="ml-auto rounded bg-default-100/60 px-1.5 py-0.5 text-[0.65rem] text-default-500">权重 {e.weight}</span>
                )}
                <button onClick={() => handleDeleteEdge(e.subject, e.predicate, e.object)}
                  className="ml-1 text-default-500 hover:text-destructive" title="删除关系"><Trash2 className="h-3.5 w-3.5" /></button>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* ═══ 空状态 ═══ */}
      {!loading && nodes.length === 0 && edges.length === 0 && (
        <Card title="图谱为空">
          <div className="flex flex-col items-center py-6 text-center">
            <GitGraph className="h-10 w-10 text-default-500/30 mb-3" />
            <p className="text-sm text-default-500">暂无知图谱数据</p>
            <p className="text-xs text-default-500 mt-1">导入知识后会自动构建实体关系</p>
          </div>
        </Card>
      )}

      {/* ═══ 添加节点 ═══ */}
      {subTab === "nodes" && <AddNodeForm onAdded={load} />}
      {/* ═══ 添加关系 ═══ */}
      {subTab === "edges" && <AddEdgeForm nodes={nodes} onAdded={load} />}
    </div>
  )
}

function GraphCanvas({ nodes, edges }: { nodes: GraphNode[]; edges: GraphEdge[] }) {
  const { visibleNodes, visibleEdges, positions } = graphLayout(nodes, edges)
  return (
    <Card title={`图谱视图 (${visibleNodes.length}/${nodes.length} 节点)`}>
      <div className="h-[390px] overflow-hidden rounded-xl border border-white/10 bg-[radial-gradient(circle_at_50%_45%,hsl(188.5_45%_13%),hsl(222.2_70%_5%))]">
        <svg viewBox="0 0 720 370" className="h-full w-full" role="img" aria-label="知识图谱可视化">
          <g opacity="0.52">
            {visibleEdges.map((edge, index) => {
              const source = positions.get(edge.subject)
              const target = positions.get(edge.object)
              if (!source || !target) return null
              return (
                <line
                  key={`${edge.hash || edge.subject + edge.object}-${index}`}
                  x1={source.x}
                  y1={source.y}
                  x2={target.x}
                  y2={target.y}
                  stroke="hsl(160 60% 50%)"
                  strokeWidth={Math.max(0.8, Math.min(3.2, Number(edge.weight ?? 1)))}
                />
              )
            })}
          </g>
          <g>
            {visibleNodes.map((node, index) => {
              const pos = positions.get(node.name)
              if (!pos) return null
              const size = Math.max(5, Math.min(13, 5 + Math.log2((node.count ?? 1) + 1)))
              return (
                <g key={node.name} transform={`translate(${pos.x} ${pos.y})`}>
                  <circle r={size + 4} fill="hsl(188.5 100% 45.5%)" opacity="0.12" />
                  <circle r={size} fill={index % 4 === 0 ? "hsl(280 65% 65%)" : "hsl(188.5 100% 45.5%)"} />
                  <text
                    x={size + 6}
                    y="4"
                    className="fill-foreground text-[10px] font-medium"
                  >
                    {node.name.length > 18 ? `${node.name.slice(0, 18)}...` : node.name}
                  </text>
                </g>
              )
            })}
          </g>
        </svg>
      </div>
      {nodes.length > visibleNodes.length && (
        <p className="mt-2 text-xs text-default-500">为保证流畅，仅渲染前 {visibleNodes.length} 个节点；完整数据可在节点和关系列表查看。</p>
      )}
    </Card>
  )
}

function AddNodeForm({ onAdded }: { onAdded: () => void }) {
  const { toast } = useToast()
  const [name, setName] = useState("")
  const [type, setType] = useState("entity")

  const handleAdd = async () => {
    if (!name.trim()) return
    try { await createGraphNode(name.trim(), type); toast("节点已添加", "success"); setName(""); onAdded() } catch { toast("添加失败", "error") }
  }

  return (
    <Card title="添加节点">
      <div className="flex flex-wrap gap-2">
        <input type="text" value={name} onChange={(e) => setName(e.target.value)}
          placeholder="节点名称" onKeyDown={(e) => e.key === "Enter" && handleAdd()}
          className="h-9 flex-1 rounded-xl border border-white/10 bg-transparent px-3 text-sm text-default-900 placeholder:text-default-500 focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
        />
        <select value={type} onChange={(e) => setType(e.target.value)}
          className="h-9 rounded-xl border border-white/10 bg-transparent px-3 text-sm text-default-900 cursor-pointer">
          <option value="entity">实体</option><option value="concept">概念</option>
          <option value="character">角色</option><option value="item">物品</option>
          <option value="location">地点</option>
        </select>
        <Button onClick={handleAdd}><Plus className="h-4 w-4" />添加</Button>
      </div>
    </Card>
  )
}

function AddEdgeForm({ nodes, onAdded }: { nodes: GraphNode[]; onAdded: () => void }) {
  const { toast } = useToast()
  const [sub, setSub] = useState("")
  const [pred, setPred] = useState("")
  const [obj, setObj] = useState("")
  const [weight, setWeight] = useState("1.0")

  const handleAdd = async () => {
    if (!sub || !pred || !obj) return
    try { await createGraphEdge(sub, pred, obj, parseFloat(weight) || 1); toast("关系已添加", "success"); setSub(""); setPred(""); setObj(""); setWeight("1.0"); onAdded() } catch { toast("添加失败", "error") }
  }

  return (
    <Card title="添加关系">
      <div className="flex flex-wrap items-end gap-2">
        <input type="text" value={sub} onChange={(e) => setSub(e.target.value)}
          placeholder="主语" list="nodes-sub"
          className="h-9 flex-1 min-w-[120px] rounded-xl border border-white/10 bg-transparent px-3 text-sm text-default-900 placeholder:text-default-500 focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
        />
        <input type="text" value={pred} onChange={(e) => setPred(e.target.value)}
          placeholder="谓词(关系)"
          className="h-9 flex-1 min-w-[120px] rounded-xl border border-white/10 bg-transparent px-3 text-sm text-default-900 placeholder:text-default-500 focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
        />
        <input type="text" value={obj} onChange={(e) => setObj(e.target.value)}
          placeholder="宾语" list="nodes-obj"
          className="h-9 flex-1 min-w-[120px] rounded-xl border border-white/10 bg-transparent px-3 text-sm text-default-900 placeholder:text-default-500 focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
        />
        <input type="number" value={weight} onChange={(e) => setWeight(e.target.value)}
          step="0.1" min="0" max="10"
          className="h-9 w-20 rounded-xl border border-white/10 bg-transparent px-3 text-sm text-default-900 focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
        />
        <Button onClick={handleAdd}><Plus className="h-4 w-4" />添加</Button>
      </div>
      <datalist id="nodes-sub">{nodes.map((n) => <option key={n.name} value={n.name} />)}</datalist>
      <datalist id="nodes-obj">{nodes.map((n) => <option key={n.name} value={n.name} />)}</datalist>
    </Card>
  )
}
