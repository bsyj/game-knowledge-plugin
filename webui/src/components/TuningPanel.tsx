import { useEffect, useState, useCallback } from "react"
import { RefreshCw, SlidersHorizontal, Play, X, Undo2, CheckCircle, Clock, AlertTriangle } from "lucide-react"
import {
  fetchTuningProfile,
  fetchTuningTasks,
  createTuningTask,
  cancelTuningTask,
  applyBestTuningProfile,
  applyTuningProfile,
  rollbackTuningProfile,
} from "@/lib/api"
import { useToast } from "@/components/Toast"
import Card from "@/components/Card"
import Button from "@/components/Button"
import Loading from "@/components/Loading"

interface TuningTask {
  task_id?: string
  status?: string
  created_at?: number | string
  updated_at?: number | string
  summary?: string
  rounds_completed?: number
  rounds_total?: number
  best_score?: number
  profile_snapshot?: Record<string, unknown>
}

const STATUS_ICON: Record<string, React.ReactNode> = {
  completed: <CheckCircle className="h-3.5 w-3.5 text-chart-2" />,
  running: <Clock className="h-3.5 w-3.5 text-chart-3 animate-pulse" />,
  pending: <Clock className="h-3.5 w-3.5 text-default-500" />,
  cancelled: <X className="h-3.5 w-3.5 text-destructive" />,
  failed: <AlertTriangle className="h-3.5 w-3.5 text-destructive" />,
}

const STATUS_LABEL: Record<string, string> = {
  completed: "已完成",
  running: "运行中",
  pending: "等待中",
  cancelled: "已取消",
  failed: "失败",
}

export default function TuningPanel() {
  const { toast } = useToast()
  const [profile, setProfile] = useState<Record<string, unknown> | null>(null)
  const [tasks, setTasks] = useState<TuningTask[]>([])
  const [loading, setLoading] = useState(false)
  const [creating, setCreating] = useState(false)
  const [editingProfile, setEditingProfile] = useState(false)
  const [profileText, setProfileText] = useState("")

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [p, t] = await Promise.all([fetchTuningProfile(), fetchTuningTasks()])
      const pd = p as { profile?: Record<string, unknown>; settings?: Record<string, unknown>; success?: boolean }
      const td = t as { items?: TuningTask[]; success?: boolean }
      setProfile((pd.profile || pd.settings || pd) as Record<string, unknown>)
      setTasks((td.items || []) as TuningTask[])
    } catch {
      toast("加载调优数据失败", "error")
    } finally {
      setLoading(false)
    }
  }, [toast])

  useEffect(() => { load() }, [load])

  const handleCreateTask = async () => {
    setCreating(true)
    try {
      await createTuningTask({ mode: "auto" })
      toast("调优任务已创建", "success")
      load()
    } catch {
      toast("创建任务失败", "error")
    } finally {
      setCreating(false)
    }
  }

  const handleCancelTask = async (taskId: string) => {
    try {
      await cancelTuningTask(taskId)
      toast("任务已取消", "success")
      load()
    } catch {
      toast("取消失败", "error")
    }
  }

  const handleApplyBest = async (taskId: string) => {
    try {
      await applyBestTuningProfile(taskId)
      toast("已应用最优配置", "success")
      load()
    } catch {
      toast("应用失败", "error")
    }
  }

  const handleApplyProfile = async () => {
    try {
      const parsed = JSON.parse(profileText)
      await applyTuningProfile(parsed)
      toast("配置已应用", "success")
      setEditingProfile(false)
      load()
    } catch {
      toast("配置格式无效或应用失败", "error")
    }
  }

  const handleRollback = async () => {
    try {
      await rollbackTuningProfile()
      toast("已回滚", "success")
      load()
    } catch {
      toast("回滚失败", "error")
    }
  }

  return (
    <div className="space-y-5">
      {/* 当前调优配置 */}
      <Card
        title="当前调优配置"
        actions={
          <>
            <Button variant="outline" size="sm" onClick={handleRollback}>
              <Undo2 className="h-3 w-3" />回滚
            </Button>
            <Button variant="outline" size="sm" onClick={() => { setProfileText(JSON.stringify(profile, null, 2)); setEditingProfile(true) }}>
              <SlidersHorizontal className="h-3 w-3" />编辑
            </Button>
            <Button variant="outline" size="sm" onClick={load}>
              <RefreshCw className="h-3 w-3" />刷新
            </Button>
          </>
        }
      >
        {loading ? <Loading />
        : !profile ? <p className="text-sm text-default-500">暂无调优配置</p>
        : (
          <div className="space-y-3">
            <div className="rounded-xl border border-white/10 bg-content1/45 p-4">
              <pre className="max-h-80 overflow-auto text-xs leading-relaxed whitespace-pre-wrap font-mono">
                {JSON.stringify(profile, null, 2)}
              </pre>
            </div>
            {editingProfile && (
              <div className="space-y-2 rounded-xl border border-ring/50 bg-content1/45 p-3">
                <textarea
                  className="w-full h-48 rounded-md border border-white/10 bg-content1/45 px-3 py-2 text-xs font-mono text-default-900 resize-y"
                  value={profileText}
                  onChange={(e) => setProfileText(e.target.value)}
                />
                <div className="flex gap-2">
                  <Button size="sm" onClick={handleApplyProfile}>应用</Button>
                  <Button variant="outline" size="sm" onClick={() => setEditingProfile(false)}>取消</Button>
                </div>
              </div>
            )}
          </div>
        )}
      </Card>

      {/* 调优任务 */}
      <Card
        title="调优任务"
        actions={
          <Button variant="outline" size="sm" onClick={handleCreateTask} disabled={creating}>
            <Play className="h-3 w-3" />{creating ? "创建中..." : "新建任务"}
          </Button>
        }
      >
        {tasks.length === 0 ? (
          <p className="text-sm text-default-500">暂无调优任务，点击"新建任务"开始</p>
        ) : (
          <div className="space-y-2">
            {tasks.map((task) => (
              <div key={task.task_id || String(task.created_at)} className="rounded-xl border border-white/10 bg-content1/45 p-3">
                <div className="flex items-center justify-between flex-wrap gap-2">
                  <div className="flex items-center gap-2 min-w-0">
                    {STATUS_ICON[task.status || "pending"] || STATUS_ICON.pending}
                    <span className={`text-xs font-semibold ${task.status === "completed" ? "text-chart-2" : task.status === "failed" ? "text-destructive" : "text-default-500"}`}>
                      {STATUS_LABEL[task.status || ""] || task.status || "未知"}
                    </span>
                    <code className="text-[0.65rem] text-default-500 truncate max-w-[160px]">{task.task_id || "-"}</code>
                  </div>
                  <div className="flex items-center gap-1.5">
                    {task.rounds_completed != null && (
                      <span className="text-[0.65rem] text-default-500">
                        轮次: {task.rounds_completed}{task.rounds_total != null ? `/${task.rounds_total}` : ""}
                      </span>
                    )}
                    {task.best_score != null && (
                      <span className="text-[0.65rem] text-chart-2 font-medium">
                        最佳: {Number(task.best_score).toFixed(3)}
                      </span>
                    )}
                    {task.status === "running" && (
                      <Button variant="ghost" size="sm" onClick={() => handleCancelTask(task.task_id!)}>
                        <X className="h-3 w-3" />
                      </Button>
                    )}
                    {task.status === "completed" && (
                      <Button variant="outline" size="sm" onClick={() => handleApplyBest(task.task_id!)}>
                        <CheckCircle className="h-3 w-3" />应用最优
                      </Button>
                    )}
                  </div>
                </div>
                {task.summary && (
                  <p className="mt-1 text-xs text-default-500">{task.summary}</p>
                )}
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  )
}