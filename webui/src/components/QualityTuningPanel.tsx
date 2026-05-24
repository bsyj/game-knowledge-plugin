import { useCallback, useEffect, useState } from "react"
import { BarChart3, ChevronDown, Clock3, Loader2, RefreshCw, Sparkles } from "lucide-react"
import { fetchQualityTuningCards, fetchQualityTuningTasks, runQualityTuning } from "@/lib/api"
import { useToast } from "@/components/Toast"
import Card from "@/components/Card"
import Button from "@/components/Button"
import { formatDate, truncate } from "@/lib/utils"

interface TunedCard {
  id: string | number
  title?: string
  question?: string
  answer?: string
  category?: string
  review_status?: string
  ai_review_status?: string
  ai_review_reason?: string
  ai_review_score?: number
  ai_review_issues?: string[]
  similar_cards?: Array<{ id?: string | number; title?: string; question?: string; score?: number; review_status?: string }>
  updated_at?: number
}

interface TuningRunResult {
  success?: boolean
  queued?: boolean
  task?: TuningTask
  error?: string
}

interface TuningTask {
  id: string
  status: "queued" | "running" | "completed" | "failed" | string
  limit?: number
  processed?: number
  total?: number
  progress?: number
  counts?: Record<string, number>
  error?: string
  reviewer_name?: string
  created_at?: number
  started_at?: number
  finished_at?: number
  updated_at?: number
}

const STATUS_OPTIONS = [
  { key: "", label: "全部" },
  { key: "approved", label: "通过" },
  { key: "similar", label: "疑似相似" },
  { key: "needs_answer", label: "待回答" },
  { key: "ai_rejected", label: "AI已拒绝" },
]

const STATUS_LABEL: Record<string, string> = {
  approved: "通过保留",
  similar: "疑似相似",
  needs_answer: "待回答",
  ai_rejected: "AI已拒绝",
}

const DASHBOARD_STATUSES = [
  { key: "approved", label: "通过", tone: "success" },
  { key: "similar", label: "疑似相似", tone: "secondary" },
  { key: "needs_answer", label: "待回答", tone: "warning" },
  { key: "ai_rejected", label: "AI拒绝", tone: "destructive" },
]

function statusClass(status: string) {
  if (status === "approved") return "border-success/25 bg-success/10 text-success"
  if (status === "similar") return "border-secondary/30 bg-secondary/10 text-secondary"
  if (status === "needs_answer") return "border-warning/30 bg-warning/10 text-warning"
  return "border-destructive/25 bg-destructive/10 text-destructive"
}

function statClass(tone: string) {
  if (tone === "success") return "border-success/25 bg-success/10 text-success"
  if (tone === "secondary") return "border-secondary/30 bg-secondary/10 text-secondary"
  if (tone === "warning") return "border-warning/30 bg-warning/10 text-warning"
  return "border-destructive/25 bg-destructive/10 text-destructive"
}

function countByStatus(cards: TunedCard[]) {
  return cards.reduce<Record<string, number>>((acc, card) => {
    const key = String(card.review_status || "unknown")
    acc[key] = (acc[key] || 0) + 1
    return acc
  }, {})
}

export default function QualityTuningPanel() {
  const { toast } = useToast()
  const [cards, setCards] = useState<TunedCard[]>([])
  const [status, setStatus] = useState("")
  const [limit, setLimit] = useState(10)
  const [loading, setLoading] = useState(false)
  const [taskLoading, setTaskLoading] = useState(false)
  const [running, setRunning] = useState(false)
  const [tasks, setTasks] = useState<TuningTask[]>([])
  const visibleCounts = countByStatus(cards)
  const visibleTotal = cards.length
  const reviewedTotal = DASHBOARD_STATUSES.reduce((sum, item) => sum + (visibleCounts[item.key] || 0), 0)
  const latestTask = tasks[0]
  const latestCounts = latestTask?.counts || null
  const activeTasks = tasks.filter((task) => task.status === "queued" || task.status === "running")
  const lastTotal = latestCounts ? Object.values(latestCounts).reduce((sum, value) => sum + Number(value || 0), 0) : 0

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await fetchQualityTuningCards({ status, limit: 80 }) as { cards?: TunedCard[] }
      setCards(Array.isArray(data.cards) ? data.cards : [])
    } catch {
      toast("加载随机调优结果失败", "error")
    } finally {
      setLoading(false)
    }
  }, [status, toast])

  const loadTasks = useCallback(async (silent = false) => {
    if (!silent) setTaskLoading(true)
    try {
      const data = await fetchQualityTuningTasks(30) as { tasks?: TuningTask[] }
      setTasks(Array.isArray(data.tasks) ? data.tasks : [])
    } catch {
      if (!silent) toast("加载随机调优队列失败", "error")
    } finally {
      if (!silent) setTaskLoading(false)
    }
  }, [toast])

  useEffect(() => {
    void load()
    void loadTasks()
  }, [load, loadTasks])

  useEffect(() => {
    const timer = window.setInterval(() => {
      void loadTasks(true)
      if (activeTasks.length > 0) void load()
    }, activeTasks.length > 0 ? 2500 : 8000)
    return () => window.clearInterval(timer)
  }, [activeTasks.length, load, loadTasks])

  const handleRun = async () => {
    if (running) return
    setRunning(true)
    try {
      const data = await runQualityTuning({ limit }) as TuningRunResult
      if (data.success === false) throw new Error(data.error || "随机调优失败")
      toast(`随机调优任务已加入队列：抽 ${data.task?.limit || limit} 张`, "success")
      await loadTasks(true)
    } catch (error) {
      toast(error instanceof Error ? error.message : "随机调优失败", "error")
    } finally {
      setRunning(false)
    }
  }

  return (
    <Card
      title="随机调优"
      className="flex min-h-0 flex-col overflow-hidden md:h-full"
      actions={
        <>
          <select
            className="h-8 rounded-md border border-white/10 bg-content1/45 px-2 text-xs outline-none focus:border-primary"
            value={limit}
            onChange={(event) => setLimit(Number(event.target.value))}
            disabled={running}
          >
            {[5, 10, 20, 30, 50].map((item) => <option key={item} value={item}>抽 {item} 张</option>)}
          </select>
          <Button variant="primary" size="sm" onClick={handleRun} disabled={running}>
            {running ? <Loader2 className="h-3 w-3 animate-spin" /> : <Sparkles className="h-3 w-3" />}
            {running ? "入队中" : "随机调优"}
          </Button>
          <Button variant="outline" size="sm" onClick={() => { void load(); void loadTasks() }} disabled={loading || taskLoading}>
            <RefreshCw className={`h-3 w-3 ${loading || taskLoading ? "animate-spin" : ""}`} />
          </Button>
        </>
      }
    >
      <div className="mb-3 grid shrink-0 gap-2 md:grid-cols-[1fr_auto]">
        <div className="flex flex-wrap gap-1.5">
          {STATUS_OPTIONS.map((item) => (
            <button
              key={item.key || "all"}
              type="button"
              onClick={() => setStatus(item.key)}
              className={`h-8 rounded-md border px-2.5 text-xs font-semibold transition-colors ${status === item.key ? "border-primary/35 bg-primary/15 text-primary" : "border-white/10 bg-content1/45 text-default-500 hover:text-default-900"}`}
            >
              {item.label}
            </button>
          ))}
        </div>
        {latestCounts && (
          <div className="flex flex-wrap items-center gap-1.5 text-xs text-default-500">
            <span>最近任务</span>
            <span className="rounded-md border border-success/25 bg-success/10 px-1.5 py-0.5 text-success">通过 {latestCounts.approved || 0}</span>
            <span className="rounded-md border border-secondary/30 bg-secondary/10 px-1.5 py-0.5 text-secondary">相似 {latestCounts.similar || 0}</span>
            <span className="rounded-md border border-warning/30 bg-warning/10 px-1.5 py-0.5 text-warning">待回答 {latestCounts.needs_answer || 0}</span>
            <span className="rounded-md border border-destructive/25 bg-destructive/10 px-1.5 py-0.5 text-destructive">拒绝 {latestCounts.ai_rejected || 0}</span>
          </div>
        )}
      </div>

      <div className="mb-3 grid shrink-0 gap-2 sm:grid-cols-2 xl:grid-cols-6">
        <div className="rounded-lg border border-primary/20 bg-primary/10 p-3">
          <div className="flex items-center justify-between gap-2 text-xs font-semibold text-primary">
            <span>当前结果</span>
            <BarChart3 className="h-3.5 w-3.5" />
          </div>
          <div className="mt-2 text-2xl font-semibold text-default-900">{visibleTotal}</div>
          <div className="mt-0.5 text-[0.7rem] text-default-500">已归类 {reviewedTotal} 张</div>
        </div>
        {DASHBOARD_STATUSES.map((item) => (
          <div key={item.key} className={`rounded-lg border p-3 ${statClass(item.tone)}`}>
            <div className="text-xs font-semibold">{item.label}</div>
            <div className="mt-2 text-2xl font-semibold">{visibleCounts[item.key] || 0}</div>
            <div className="mt-0.5 text-[0.7rem] opacity-75">最近任务 {latestCounts?.[item.key] || 0}</div>
          </div>
        ))}
        <div className="rounded-lg border border-white/10 bg-content1/45 p-3">
          <div className="text-xs font-semibold text-default-500">队列中</div>
          <div className="mt-2 text-2xl font-semibold text-default-900">{activeTasks.length}</div>
          <div className="mt-0.5 text-[0.7rem] text-default-500">最近处理 {latestTask ? lastTotal : "-"}</div>
        </div>
      </div>

      <div className="mb-3 shrink-0 rounded-xl border border-black/10 bg-content1/35 p-3 dark:border-white/10">
        <div className="mb-2 flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 text-sm font-semibold text-default-900">
            <Clock3 className="h-4 w-4 text-primary" />
            队列窗口
          </div>
          <span className="text-xs text-default-500">后台执行，切换页面不丢进度</span>
        </div>
        {tasks.length === 0 ? (
          <div className="rounded-lg border border-dashed border-white/10 px-3 py-4 text-center text-sm text-default-500">暂无调优任务</div>
        ) : (
          <div className="grid gap-2 lg:grid-cols-2">
            {tasks.slice(0, 4).map((task) => {
              const isActive = task.status === "queued" || task.status === "running"
              const percent = Math.max(0, Math.min(100, Math.round(Number(task.progress || 0) * 100)))
              return (
                <div key={task.id} className="rounded-lg border border-white/10 bg-content1/55 p-2.5">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-1.5">
                      <span className={`rounded-md border px-1.5 py-0.5 text-[0.65rem] font-semibold ${isActive ? "border-primary/25 bg-primary/10 text-primary" : task.status === "failed" ? "border-destructive/25 bg-destructive/10 text-destructive" : "border-success/25 bg-success/10 text-success"}`}>
                        {task.status === "queued" ? "排队中" : task.status === "running" ? "处理中" : task.status === "failed" ? "失败" : "完成"}
                      </span>
                      <span className="font-mono text-xs text-default-500">#{task.id}</span>
                    </div>
                    <span className="text-xs text-default-500">{task.processed || 0}/{task.total || task.limit || 0}</span>
                  </div>
                  <div className="mt-2 h-2 overflow-hidden rounded-full bg-default-100">
                    <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${percent}%` }} />
                  </div>
                  <div className="mt-2 flex flex-wrap gap-1 text-[0.65rem]">
                    <span className="rounded-md bg-success/10 px-1.5 py-0.5 text-success">通过 {task.counts?.approved || 0}</span>
                    <span className="rounded-md bg-secondary/10 px-1.5 py-0.5 text-secondary">相似 {task.counts?.similar || 0}</span>
                    <span className="rounded-md bg-warning/10 px-1.5 py-0.5 text-warning">待回答 {task.counts?.needs_answer || 0}</span>
                    <span className="rounded-md bg-destructive/10 px-1.5 py-0.5 text-destructive">拒绝 {task.counts?.ai_rejected || 0}</span>
                    {(task.counts?.error || 0) > 0 && <span className="rounded-md bg-destructive/10 px-1.5 py-0.5 text-destructive">错误 {task.counts?.error || 0}</span>}
                  </div>
                  {task.error && <div className="mt-2 text-xs text-destructive">{task.error}</div>}
                </div>
              )
            })}
          </div>
        )}
      </div>

      <div className="min-h-[24rem] flex-1 overflow-y-auto overscroll-contain rounded-xl border border-black/10 bg-content1/18 p-2 dark:border-white/10">
        {cards.length === 0 ? (
          <div className="flex h-full min-h-[24rem] items-center justify-center text-sm text-default-500">
            暂无随机调优结果
          </div>
        ) : (
          <div className="space-y-2">
            {cards.map((card) => {
              const cardStatus = String(card.review_status || "")
              const similarCards = Array.isArray(card.similar_cards) ? card.similar_cards.slice(0, 3) : []
              return (
                <div key={String(card.id)} className="rounded-xl border border-white/10 bg-content1/45 p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className={`rounded-md border px-1.5 py-0.5 text-[0.65rem] font-semibold ${statusClass(cardStatus)}`}>
                        {STATUS_LABEL[cardStatus] || cardStatus || "未知"}
                      </span>
                      <span className="rounded-md bg-primary/15 px-1.5 py-0.5 text-[0.65rem] font-semibold text-primary">#{card.id}</span>
                      {card.category && <span className="rounded-md border border-white/10 bg-default-100/60 px-1.5 py-0.5 text-[0.65rem] text-default-500">{card.category}</span>}
                      {typeof card.ai_review_score === "number" && <span className="rounded-md border border-white/10 bg-default-100/60 px-1.5 py-0.5 text-[0.65rem] text-default-500">AI {card.ai_review_score.toFixed(2)}</span>}
                      {similarCards.length > 0 && <span className="rounded-md border border-secondary/25 bg-secondary/10 px-1.5 py-0.5 text-[0.65rem] font-semibold text-secondary">相似 {similarCards.length}</span>}
                    </div>
                    <span className="text-[0.7rem] text-default-500">{formatDate(card.updated_at)}</span>
                  </div>
                  <details className="group mt-2">
                    <summary className="flex cursor-pointer list-none items-center justify-between gap-3 rounded-md border border-white/10 bg-default-100/45 px-2 py-1.5 text-xs font-semibold text-default-600 transition-colors hover:text-default-900">
                      <span>{card.ai_review_status || "查看折叠详情"}</span>
                      <ChevronDown className="h-3.5 w-3.5 transition-transform group-open:rotate-180" />
                    </summary>
                    <div className="mt-2 space-y-2 rounded-lg border border-white/10 bg-content1/55 p-2.5">
                      <h3 className="text-sm font-semibold text-default-900">{card.title || `卡片 #${card.id}`}</h3>
                      {card.question && <p className="whitespace-pre-wrap text-sm leading-relaxed">Q: {card.question}</p>}
                      {card.answer && <p className="whitespace-pre-wrap text-sm leading-relaxed text-default-600">A: {truncate(card.answer, 520)}</p>}
                      {card.ai_review_reason && (
                        <div className="rounded-md border border-white/10 bg-default-100/45 px-2 py-1.5 text-xs text-default-500">
                          {card.ai_review_reason}
                        </div>
                      )}
                      {similarCards.length > 0 && (
                        <div className="grid gap-1.5">
                          {similarCards.map((item, index) => (
                            <div key={`${item.id || index}`} className="rounded-md border border-secondary/25 bg-secondary/10 px-2 py-1.5 text-xs">
                              <span className="font-semibold text-secondary">相似 #{item.id || "-"}</span>
                              <span className="ml-2 text-default-500">{Math.round(Number(item.score || 0) * 100)}%</span>
                              <div className="mt-0.5 text-default-700">{truncate(item.title || item.question || "未命名卡片", 140)}</div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </details>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </Card>
  )
}
