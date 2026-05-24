import { useEffect, useState, useCallback } from "react"
import { RefreshCw, Search, Send, ShieldCheck, HardDrive, CircleCheck, AlertTriangle } from "lucide-react"
import { Chip } from "@heroui/react"
import { fetchStats, fetchRuntimeConfig, hasPermission, runtimeSelfCheck, type AuthUser } from "@/lib/api"
import { useToast } from "@/components/Toast"
import Card from "@/components/Card"
import Button from "@/components/Button"
import Loading from "@/components/Loading"
import { formatNumber } from "@/lib/utils"

const CATEGORIES: { key: string; label: string; color: string; totalKey?: string }[] = [
  { key: "auto_review_today", totalKey: "auto_review_total", label: "自动审核", color: "text-primary" },
  { key: "ai_review_today", totalKey: "ai_review_total", label: "AI复审", color: "text-chart-4" },
  { key: "card_count", label: "知识卡片", color: "text-primary" },
  { key: "searchable_card_count", totalKey: "card_count", label: "可检索卡片", color: "text-success" },
  { key: "approved_count", label: "已审核", color: "text-chart-2" },
  { key: "pending_count", label: "待审核", color: "text-chart-3" },
  { key: "ai_rejected_count", label: "AI已拒绝", color: "text-destructive" },
  { key: "node_count", label: "图谱节点", color: "text-chart-4" },
  { key: "edge_count", label: "图谱关系", color: "text-chart-5" },
  { key: "source_count", label: "知识来源", color: "text-primary" },
  { key: "total_embeddings", label: "向量总数", color: "text-chart-3" },
]

interface Props {
  onNavigate: (tab: string) => void
  user: AuthUser
}

export default function Dashboard({ onNavigate, user }: Props) {
  const { toast } = useToast()
  const [stats, setStats] = useState<Record<string, number> | null>(null)
  const [loading, setLoading] = useState(false)
  const [selfCheck, setSelfCheck] = useState<unknown>(null)
  const [checking, setChecking] = useState(false)
  const canCreate = hasPermission(user, "knowledge.create")
  const canViewCards = hasPermission(user, "cards.view")
  const canMaintain = hasPermission(user, "maintenance.manage")

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await fetchStats()
      setStats(data)
    } catch {
      toast("加载仪表盘失败", "error")
    } finally {
      setLoading(false)
    }
  }, [toast])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    if (!canMaintain) return
    fetchRuntimeConfig().then((c) => {
      const cfg = c as Record<string, unknown>
      if (cfg?.auto_save) setSelfCheck({ auto_save: true })
    }).catch(() => {})
  }, [canMaintain])

  const handleSelfCheck = async () => {
    setChecking(true)
    try {
      const data = await runtimeSelfCheck()
      setSelfCheck(data)
      toast("自检完成", "success")
    } catch {
      toast("自检失败", "error")
    } finally {
      setChecking(false)
    }
  }

  return (
    <div className="space-y-5">
      {/* ═══ Hero / 快速开始 ═══ */}
      <div className="napcat-glass relative overflow-hidden rounded-3xl p-5">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
          <div className="space-y-1.5 lg:max-w-sm">
            <Chip size="sm" color="accent" variant="soft">游戏知识库</Chip>
            <h2 className="text-xl font-bold leading-tight text-default-900">快速管理游戏知识</h2>
            <p className="text-sm text-default-500">选择操作入口开始管理你的游戏知识库</p>
          </div>
          <div className="grid w-full gap-2.5 sm:grid-cols-3 lg:max-w-3xl">
            <button
              type="button"
              onClick={() => onNavigate("search")}
              className="group flex items-start gap-3 rounded-2xl border border-white/10 bg-default-50/50 p-3.5 text-left transition hover:border-primary/45 hover:bg-default-100/70"
            >
              <div className="flex-none rounded-xl bg-primary/10 p-2 text-primary transition-transform group-hover:scale-105">
                <Search className="h-4 w-4" />
              </div>
              <div className="min-w-0">
                <div className="text-sm font-semibold">搜索知识</div>
                <div className="mt-0.5 text-xs leading-relaxed text-default-500">搜索已存储的游戏知识</div>
              </div>
            </button>
            {canCreate && (
              <button
                type="button"
                onClick={() => onNavigate("ingest")}
                className="group flex items-start gap-3 rounded-2xl border border-white/10 bg-default-50/50 p-3.5 text-left transition hover:border-warning/45 hover:bg-default-100/70"
              >
                <div className="flex-none rounded-xl bg-amber-500/10 p-2 text-amber-500 transition-transform group-hover:scale-105">
                  <Send className="h-4 w-4" />
                </div>
                <div className="min-w-0">
                  <div className="text-sm font-semibold">写入知识</div>
                  <div className="mt-0.5 text-xs leading-relaxed text-default-500">手动添加新的游戏知识</div>
                </div>
              </button>
            )}
            {canViewCards && (
              <button
                type="button"
                onClick={() => onNavigate("review")}
                className="group flex items-start gap-3 rounded-2xl border border-white/10 bg-default-50/50 p-3.5 text-left transition hover:border-secondary/45 hover:bg-default-100/70"
              >
                <div className="flex-none rounded-xl bg-violet-500/10 p-2 text-violet-500 transition-transform group-hover:scale-105">
                  <ShieldCheck className="h-4 w-4" />
                </div>
                <div className="min-w-0">
                  <div className="text-sm font-semibold">审核队列</div>
                  <div className="mt-0.5 text-xs leading-relaxed text-default-500">处理待审核与 AI 已拒绝卡片</div>
                </div>
              </button>
            )}
          </div>
        </div>
      </div>

      {/* ═══ 状态网格 ═══ */}
      {loading && !stats ? <Loading />
      : stats ? (
        <Card
          title="运行概览"
          actions={<Button variant="outline" size="sm" onClick={load}><RefreshCw className="h-3 w-3" />刷新</Button>}
        >
          <div className="grid gap-3 sm:grid-cols-4">
            {CATEGORIES.map((cat) => (
              <div
                key={cat.key}
                className="rounded-2xl border border-white/10 bg-default-50/45 p-3.5 transition-colors hover:border-primary/40"
              >
                <div className="text-xs text-default-500">{cat.label}</div>
                <div className={`mt-1 text-xl font-semibold ${cat.color}`}>
                  {cat.totalKey
                    ? `${formatNumber(stats[cat.key] ?? 0)}/${formatNumber(stats[cat.totalKey] ?? 0)}`
                    : formatNumber(stats[cat.key] ?? 0)}
                </div>
              </div>
            ))}
          </div>
        </Card>
      ) : (
        <Card title="运行概览"><p className="text-sm text-default-500">暂无数据</p></Card>
      )}

      {/* ═══ 系统状态 ═══ */}
      {canMaintain && <Card
        title="系统状态"
        actions={<Button variant="outline" size="sm" onClick={handleSelfCheck} disabled={checking}><CircleCheck className="h-3 w-3" />{checking ? "自检中…" : "自检"}</Button>}
      >
        {selfCheck !== null ? (
          <div className="space-y-2">
            {Object.entries(selfCheck as Record<string, unknown>).length === 0 ? (
              <p className="text-sm text-default-500">自检未返回数据</p>
            ) : (
              <div className="grid gap-2 sm:grid-cols-2">
                {Object.entries(selfCheck as Record<string, unknown>).map(([k, v]) => (
                  <div key={k} className="flex items-center gap-2 rounded-xl border border-white/10 bg-default-50/45 px-3 py-2 text-sm">
                    {typeof v === "boolean" && v ? <CircleCheck className="h-4 w-4 text-chart-2" /> : <AlertTriangle className="h-4 w-4 text-chart-3" />}
                    <span className="font-medium text-default-500">{k}</span>
                    <span className="ml-auto">{String(v ?? "-")}</span>
                  </div>
                ))}
              </div>
            )}
            <pre className="mt-3 max-h-48 overflow-auto rounded-2xl border border-white/10 bg-default-50/35 p-3 text-xs leading-relaxed whitespace-pre-wrap font-mono">
              {JSON.stringify(selfCheck, null, 2)}
            </pre>
          </div>
        ) : (
          <div className="flex items-center gap-2 text-sm text-default-500">
            <HardDrive className="h-4 w-4" />
            点击"自检"按钮检查系统状态
          </div>
        )}
      </Card>}
    </div>
  )
}
