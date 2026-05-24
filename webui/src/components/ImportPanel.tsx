import { useEffect, useState, useCallback, useRef } from "react"
import { RefreshCw, Upload, FileText, X, ChevronLeft, ChevronRight, Loader2, RotateCcw } from "lucide-react"
import {
  fetchImportTasks,
  fetchImportTask,
  fetchImportFiles,
  fetchImportChunks,
  cancelImportTask,
  retryImportTask,
  ingestMemory,
  type IngestPayload,
} from "@/lib/api"
import { useToast } from "@/components/Toast"
import Card from "@/components/Card"
import Button from "@/components/Button"
import Loading from "@/components/Loading"

const CHUNK_PAGE_SIZE = 20
const POLL_INTERVAL = 3000

const TASK_STATUS_LABEL: Record<string, string> = {
  queued: "排队中", preparing: "准备中", running: "运行中",
  cancel_requested: "取消中", cancelled: "已取消",
  completed: "已完成", completed_with_errors: "部分完成", failed: "失败",
}

const TASK_STATUS_COLOR: Record<string, string> = {
  running: "bg-chart-3/20 text-chart-3", completed: "bg-chart-2/20 text-chart-2",
  cancelled: "bg-default-100/60 text-default-500", failed: "bg-destructive/20 text-destructive",
  completed_with_errors: "bg-chart-4/20 text-chart-4",
}

const CHUNK_STATUS_LABEL: Record<string, string> = {
  queued: "排队中", extracting: "抽取中", writing: "写入中",
  completed: "成功", failed: "失败", cancelled: "取消",
}

function statusBadge(status: string) {
  const label = TASK_STATUS_LABEL[status] || status
  const color = TASK_STATUS_COLOR[status] || "bg-default-100/60 text-default-500"
  return <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[0.65rem] font-semibold ${color}`}>{label}</span>
}

function formatTime(ts: unknown) {
  const n = Number(ts ?? 0)
  if (!n || n <= 0) return "-"
  return new Date(n * 1000).toLocaleString("zh-CN")
}

function formatProgress(p: unknown) {
  const n = Number(p ?? 0)
  return `${(n * 100).toFixed(1)}%`
}

function chunkSummary(d: unknown, t: unknown, f: unknown, c: unknown = 0) {
  const done = Number(d ?? 0), total = Number(t ?? 0), failed = Number(f ?? 0), cancelled = Number(c ?? 0)
  const parts = [`成功 ${done} / ${total} 分块`]
  if (failed > 0) parts.push(`失败 ${failed}`)
  if (cancelled > 0) parts.push(`取消 ${cancelled}`)
  return parts.join(" · ")
}

interface ImportTaskItem {
  task_id: string; task_kind?: string; mode?: string; status?: string
  current_step?: string; progress?: number; total_chunks?: number; done_chunks?: number
  failed_chunks?: number; cancelled_chunks?: number; file_count?: number
  created_at?: number; updated_at?: number; params?: Record<string, unknown>
}

interface ImportFileItem {
  file_id: string; name?: string; status?: string; current_step?: string
  progress?: number; total_chunks?: number; done_chunks?: number
  failed_chunks?: number; cancelled_chunks?: number; error?: string
}

interface ImportChunkItem {
  chunk_id: string; index?: number; status?: string; step?: string
  progress?: number; error?: string; content_preview?: string
}

export default function ImportPanel() {
  const { toast } = useToast()
  const [loading, setLoading] = useState(false)
  const [tasks, setTasks] = useState<ImportTaskItem[]>([])
  const [autoPoll, setAutoPoll] = useState(true)
  const pollRef = useRef<ReturnType<typeof setInterval>>(undefined)

  const [pasteText, setPasteText] = useState("")
  const [creating, setCreating] = useState(false)

  const [selectedTaskId, setSelectedTaskId] = useState("")
  const [taskDetail, setTaskDetail] = useState<ImportTaskItem | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState("")

  const [files, setFiles] = useState<ImportFileItem[]>([])
  const [selectedFileId, setSelectedFileId] = useState("")

  const [chunks, setChunks] = useState<ImportChunkItem[]>([])
  const [chunkTotal, setChunkTotal] = useState(0)
  const [chunkOffset, setChunkOffset] = useState(0)
  const [chunksLoading, setChunksLoading] = useState(false)

  const loadTasks = useCallback(async () => {
    try {
      const data = await fetchImportTasks(100) as { items?: ImportTaskItem[]; success?: boolean }
      setTasks((data.items || []) as ImportTaskItem[])
    } catch { /* silent */ }
  }, [])

  const loadChunks = useCallback(async (taskId: string, fileId: string, offset: number) => {
    if (!fileId) return
    setChunksLoading(true)
    try {
      const data = await fetchImportChunks(taskId, fileId, offset, CHUNK_PAGE_SIZE) as {
        chunks?: ImportChunkItem[]; items?: ImportChunkItem[]; total?: number; count?: number; success?: boolean
      }
      setChunks(((data as Record<string, unknown>).chunks || (data as Record<string, unknown>).items || []) as ImportChunkItem[])
      setChunkTotal(Number((data as Record<string, unknown>).total ?? (data as Record<string, unknown>).count ?? 0))
      setChunkOffset(offset)
    } catch {
      setChunks([])
    } finally {
      setChunksLoading(false)
    }
  }, [])

  const loadDetail = useCallback(async (taskId: string, preferredFileId = "") => {
    setDetailLoading(true)
    setDetailError("")
    try {
      const data = await fetchImportTask(taskId, false) as Record<string, unknown>
      if (!data || !(data as Record<string, unknown>).success) {
        setDetailError("加载失败")
        setTaskDetail(null)
        return
      }
      setTaskDetail((data as Record<string, unknown>).task as ImportTaskItem)
      const fd = await fetchImportFiles(taskId) as { files?: ImportFileItem[]; success?: boolean }
      const filesList = (fd.files || []) as ImportFileItem[]
      setFiles(filesList)
      const validPreferred = preferredFileId && filesList.some((file) => file.file_id === preferredFileId) ? preferredFileId : ""
      if (filesList.length > 0 && !validPreferred) {
        const newFileId = filesList[0].file_id
        setSelectedFileId(newFileId)
        loadChunks(taskId, newFileId, 0)
      } else if (validPreferred) {
        setSelectedFileId(validPreferred)
        loadChunks(taskId, validPreferred, 0)
      } else {
        setChunks([])
        setChunkTotal(0)
        setChunkOffset(0)
      }
    } catch {
      setDetailError("加载异常")
      setTaskDetail(null)
    } finally {
      setDetailLoading(false)
    }
  }, [loadChunks])

  const selectTask = useCallback((taskId: string) => {
    setSelectedTaskId(taskId)
    setSelectedFileId("")
    setFiles([])
    setChunks([])
    setChunkTotal(0)
    setChunkOffset(0)
    if (taskId) loadDetail(taskId, "")
  }, [loadDetail])

  // 初始加载 + 轮询
  useEffect(() => { loadTasks() }, [loadTasks])
  useEffect(() => {
    if (autoPoll) {
      pollRef.current = setInterval(loadTasks, POLL_INTERVAL)
      return () => { if (pollRef.current) clearInterval(pollRef.current) }
    }
  }, [autoPoll, loadTasks])

  // 选中任务变化时刷新
  useEffect(() => {
    if (selectedTaskId && !detailLoading) {
      const t = tasks.find((tk) => tk.task_id === selectedTaskId)
      if (t && (t.status === "running" || t.status === "queued" || t.status === "preparing")) {
        const interval = setInterval(() => loadDetail(selectedTaskId, selectedFileId), POLL_INTERVAL)
        return () => clearInterval(interval)
      }
    }
  }, [selectedTaskId, selectedFileId, tasks, detailLoading, loadDetail])

  const handlePaste = async () => {
    if (!pasteText.trim()) return
    setCreating(true)
    try {
      const payload: IngestPayload = {
        text: pasteText.trim(),
        source_type: "game_knowledge_web_import",
      }
      await ingestMemory(payload)
      toast("文本导入任务已创建", "success")
      setPasteText("")
      loadTasks()
    } catch {
      toast("创建任务失败", "error")
    } finally {
      setCreating(false)
    }
  }

  const handleCancel = async () => {
    if (!selectedTaskId) return
    try {
      await cancelImportTask(selectedTaskId)
      toast("取消请求已发送", "success")
      loadTasks()
    } catch { toast("取消失败", "error") }
  }

  const handleRetry = async () => {
    if (!selectedTaskId) return
    try {
      await retryImportTask(selectedTaskId)
      toast("重试已发起", "success")
      loadTasks()
      loadDetail(selectedTaskId, selectedFileId)
    } catch { toast("重试失败", "error") }
  }

  const selectFile = (fileId: string) => {
    setSelectedFileId(fileId)
    loadChunks(selectedTaskId, fileId, 0)
  }

  const moveChunkPage = (dir: -1 | 1) => {
    const newOffset = chunkOffset + dir * CHUNK_PAGE_SIZE
    if (newOffset < 0 || newOffset >= chunkTotal) return
    loadChunks(selectedTaskId, selectedFileId, newOffset)
  }

  const canPrev = chunkOffset > 0
  const canNext = chunkOffset + CHUNK_PAGE_SIZE < chunkTotal

  const runningTasks = tasks.filter((t) => t.status === "running" || t.status === "preparing")
  const queuedTasks = tasks.filter((t) => t.status === "queued")
  const recentTasks = tasks.filter((t) => !["running", "preparing", "queued"].includes(t.status || ""))

  return (
    <div className="space-y-5">
      {/* ═══ 上部分：创建任务 + 任务队列 ═══ */}
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">

        {/* 左侧：创建任务 */}
        <Card
          title="创建导入任务"
        >
          <div className="space-y-4">
            <div className="rounded-xl border bg-content1/50 p-3 sm:p-4">
              <div className="flex items-center gap-2 mb-3">
                <FileText className="h-4 w-4 text-default-500" />
                <span className="text-sm font-medium">粘贴游戏知识文本</span>
              </div>
              <div className="space-y-3">
                <textarea
                  value={pasteText}
                  onChange={(e) => setPasteText(e.target.value)}
                  placeholder="粘贴群聊记录、游戏攻略文本等..."
                  className="w-full min-h-[120px] rounded-xl border border-white/10 bg-content1/45 px-3 py-2 text-xs text-default-900 placeholder:text-default-500/60 focus:outline-none focus:ring-1 focus:ring-primary resize-y"
                />
                <Button onClick={handlePaste} disabled={creating || !pasteText.trim()}>
                  {creating ? "创建中..." : `${`导入文本`}`}
                </Button>
              </div>
            </div>
            <p className="text-xs text-default-500">导入的文本会自动分块处理，确保不超过 embedding 模型限制。</p>
          </div>
        </Card>

        {/* 右侧：任务队列 */}
        <Card
          title="导入队列"
          actions={
            <div className="flex flex-wrap items-center gap-2">
              <label className="flex min-w-0 items-center gap-1.5 text-xs text-default-500 cursor-pointer select-none">
                <input type="checkbox" checked={autoPoll} onChange={(e) => setAutoPoll(e.target.checked)} className="h-3 w-3 rounded border-white/10" />
                自动刷新 {POLL_INTERVAL / 1000}s
              </label>
              <Button variant="outline" size="sm" onClick={loadTasks}>
                <RefreshCw className="h-3 w-3" />刷新
              </Button>
            </div>
          }
        >
          <div className="space-y-3">
            {/* 运行中 */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium">运行中</span>
                <span className="text-[0.65rem] text-default-500">{runningTasks.length}</span>
              </div>
              {runningTasks.length > 0 ? (
                <div className="max-h-[160px] overflow-y-auto space-y-1.5 rounded-xl border bg-default-100/10 p-2">
                  {runningTasks.map((task) => (
                    <TaskCard key={task.task_id} task={task} selected={task.task_id === selectedTaskId} onClick={() => selectTask(task.task_id)} showProgress />
                  ))}
                </div>
              ) : <div className="rounded-xl border bg-default-100/10 p-3 text-xs text-default-500">暂无运行任务</div>}
            </div>

            {/* 排队中 */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium">排队中</span>
                <span className="text-[0.65rem] text-default-500">{queuedTasks.length}</span>
              </div>
              {queuedTasks.length > 0 ? (
                <div className="max-h-[120px] overflow-y-auto space-y-1.5 rounded-xl border bg-default-100/10 p-2">
                  {queuedTasks.map((task) => (
                    <TaskCard key={task.task_id} task={task} selected={task.task_id === selectedTaskId} onClick={() => selectTask(task.task_id)} />
                  ))}
                </div>
              ) : <div className="rounded-xl border bg-default-100/10 p-3 text-xs text-default-500">暂无排队任务</div>}
            </div>

            {/* 历史 */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium">历史</span>
                <span className="text-[0.65rem] text-default-500">{recentTasks.length}</span>
              </div>
              {recentTasks.length > 0 ? (
                <div className="max-h-[180px] overflow-y-auto space-y-1.5 rounded-xl border bg-default-100/10 p-2">
                  {recentTasks.slice(0, 20).map((task) => (
                    <TaskCard key={task.task_id} task={task} selected={task.task_id === selectedTaskId} onClick={() => selectTask(task.task_id)} />
                  ))}
                </div>
              ) : <div className="rounded-xl border bg-default-100/10 p-3 text-xs text-default-500">暂无历史任务</div>}
            </div>
          </div>
        </Card>
      </div>

      {/* ═══ 下部：任务详情 ═══ */}
      <Card
        title="任务详情"
        actions={
          <div className="flex w-full flex-wrap gap-1.5 sm:w-auto">
            <Button className="flex-1 sm:flex-none" variant="outline" size="sm" onClick={handleCancel} disabled={!selectedTaskId}>
              <X className="h-3 w-3" />取消任务
            </Button>
            <Button className="flex-1 sm:flex-none" variant="outline" size="sm" onClick={handleRetry} disabled={!selectedTaskId}>
              <RotateCcw className="h-3 w-3" />重试失败项
            </Button>
          </div>
        }
      >
        {detailLoading ? <Loading />
        : !taskDetail ? (
          <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed bg-default-100/15 px-6 py-10 text-center">
            <Loader2 className="h-5 w-5 text-default-500" />
            <p className="text-sm text-default-500">{selectedTaskId ? `加载中...` : "在队列中点击任务卡片查看详情"}</p>
          </div>
        ) : (
          <div className="space-y-5">
            {detailError && <p className="text-xs text-destructive">{detailError}</p>}

            {/* 任务摘要 */}
              <div className="overflow-auto overscroll-x-contain rounded-xl border bg-default-100/10">
              <table className="min-w-[640px] w-full text-xs">
                <tbody>
                  <tr className="border-b border-white/10">
                    <td className="w-[120px] px-3 py-2 text-default-500 font-medium">任务 ID</td>
                    <td className="px-3 py-2 font-mono text-[0.65rem] break-all">{taskDetail.task_id}</td>
                  </tr>
                  <tr className="border-b border-white/10">
                    <td className="px-3 py-2 text-default-500 font-medium">任务类型</td>
                    <td className="px-3 py-2">{taskDetail.task_kind || taskDetail.mode || "-"}</td>
                  </tr>
                  <tr className="border-b border-white/10">
                    <td className="px-3 py-2 text-default-500 font-medium">状态 / 步骤</td>
                    <td className="px-3 py-2">
                      <div className="flex items-center gap-2">
                        {statusBadge(taskDetail.status || "")}
                        <span className="text-default-500">{taskDetail.current_step || "-"}</span>
                      </div>
                    </td>
                  </tr>
                  <tr className="border-b border-white/10">
                    <td className="px-3 py-2 text-default-500 font-medium">进度</td>
                    <td className="px-3 py-2">
                      <div className="flex items-center gap-2">
                        <span>{formatProgress(taskDetail.progress)}</span>
                        <span className="text-default-500">
                          {chunkSummary(taskDetail.done_chunks, taskDetail.total_chunks, taskDetail.failed_chunks, taskDetail.cancelled_chunks)}
                        </span>
                      </div>
                    </td>
                  </tr>
                  <tr className="border-b border-white/10">
                    <td className="px-3 py-2 text-default-500 font-medium">创建时间</td>
                    <td className="px-3 py-2">{formatTime(taskDetail.created_at)}</td>
                  </tr>
                  <tr>
                    <td className="px-3 py-2 text-default-500 font-medium">更新时间</td>
                    <td className="px-3 py-2">{formatTime(taskDetail.updated_at)}</td>
                  </tr>
                </tbody>
              </table>
            </div>

            {/* 文件状态 */}
            <div>
              <div className="text-sm font-medium mb-2">文件状态</div>
              {files.length > 0 ? (
                <div className="max-h-[220px] overflow-y-auto space-y-1.5 rounded-xl border bg-default-100/10 p-2">
                  {files.map((file) => (
                    <button
                      key={file.file_id}
                      type="button"
                      onClick={() => selectFile(file.file_id)}
                      className={`w-full rounded-xl border p-3 text-left transition-all ${
                        file.file_id === selectedFileId
                          ? "border-ring/70 bg-ring/5"
                          : "bg-content1/55 hover:border-default-500/40"
                      }`}
                    >
                      <div className="flex items-center justify-between flex-wrap gap-2">
                        <span className="text-xs font-medium truncate max-w-[200px]">{file.name || file.file_id}</span>
                        {statusBadge(file.status || "")}
                      </div>
                      <div className="mt-1.5 flex flex-wrap items-center justify-between gap-1 text-[0.6rem] text-default-500">
                        <span>{file.current_step || "-"}</span>
                        <span>
                          {formatProgress(file.progress)} · {chunkSummary(file.done_chunks, file.total_chunks, file.failed_chunks, file.cancelled_chunks)}
                        </span>
                      </div>
                      <div className="mt-1 h-1 w-full rounded-full bg-secondary overflow-hidden">
                        <div
                          className={`h-full rounded-full transition-all duration-300 ${
                            file.status === "completed" ? "bg-chart-2"
                            : file.status === "failed" ? "bg-destructive"
                            : "bg-chart-3"
                          }`}
                          style={{ width: `${Math.min(100, Math.max(0, Number(file.progress ?? 0) * 100))}%` }}
                        />
                      </div>
                      {file.error && <p className="mt-1.5 text-[0.6rem] text-destructive truncate">{file.error}</p>}
                    </button>
                  ))}
                </div>
              ) : (
                <div className="rounded-xl border bg-default-100/10 p-3 text-xs text-default-500">{selectedTaskId ? "暂无文件明细" : "选择任务查看文件状态"}</div>
              )}
            </div>

            {/* 分块状态 */}
            <div>
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <span className="text-sm font-medium">分块状态</span>
                {chunkTotal > 0 && (
                  <div className="flex items-center gap-1.5 text-xs text-default-500">
                    <Button variant="outline" size="sm" onClick={() => moveChunkPage(-1)} disabled={!canPrev}>
                      <ChevronLeft className="h-3.5 w-3.5" />
                    </Button>
                    <span>{chunkOffset + 1}-{Math.min(chunkOffset + CHUNK_PAGE_SIZE, chunkTotal)} / {chunkTotal}</span>
                    <Button variant="outline" size="sm" onClick={() => moveChunkPage(1)} disabled={!canNext}>
                      <ChevronRight className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                )}
              </div>

              <div className="overflow-auto overscroll-x-contain rounded-xl border bg-content1/55">
                <table className="min-w-[640px] w-full text-xs">
                  <thead>
                    <tr className="border-b border-white/10 bg-default-100/30">
                      <th className="px-3 py-2 text-left font-medium w-[60px]">序号</th>
                      <th className="px-3 py-2 text-left font-medium w-[80px]">状态</th>
                      <th className="px-3 py-2 text-left font-medium w-[80px]">步骤</th>
                      <th className="px-3 py-2 text-left font-medium w-[70px]">进度</th>
                      <th className="px-3 py-2 text-left font-medium">错误 / 预览</th>
                    </tr>
                  </thead>
                  <tbody>
                    {chunksLoading ? (
                      <tr><td colSpan={5} className="px-3 py-4 text-center text-default-500">加载中...</td></tr>
                    ) : chunks.length > 0 ? (
                      chunks.map((chunk) => (
                        <tr key={chunk.chunk_id} className="border-b border-white/10 hover:bg-default-100/10 transition-colors">
                          <td className="px-3 py-2">{chunk.index}</td>
                          <td className="px-3 py-2">
                            <span className={`inline-flex items-center rounded-full px-1.5 py-0.5 text-[0.6rem] font-semibold ${
                              chunk.status === "completed" ? "bg-chart-2/20 text-chart-2"
                              : chunk.status === "failed" ? "bg-destructive/20 text-destructive"
                              : "bg-default-100/60 text-default-500"
                            }`}>
                              {CHUNK_STATUS_LABEL[chunk.status || ""] || chunk.status || "-"}
                            </span>
                          </td>
                          <td className="px-3 py-2 text-default-500">{chunk.step || "-"}</td>
                          <td className="px-3 py-2">{formatProgress(chunk.progress)}</td>
                          <td className="px-3 py-2 max-w-[300px]">
                            <div className="space-y-1.5">
                              {String(chunk.error ?? "").trim() ? (
                                <div className="rounded-md border border-destructive/30 bg-destructive/5 px-2 py-1 text-xs leading-relaxed text-destructive">
                                  {chunk.error}
                                </div>
                              ) : null}
                              <details className="rounded-md border bg-default-100/20 px-2 py-1 text-xs text-default-500">
                                <summary className="cursor-pointer font-medium text-default-900">
                                  {String(chunk.error ?? "").trim() ? "查看错误分块" : "查看内容详情"}
                                </summary>
                                <div className="mt-1 whitespace-pre-wrap break-words leading-relaxed">
                                  {String(chunk.content_preview ?? "-") || "-"}
                                </div>
                              </details>
                            </div>
                          </td>
                        </tr>
                      ))
                    ) : (
                      <tr><td colSpan={5} className="px-3 py-4 text-center text-default-500">暂无分块数据</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}
      </Card>
    </div>
  )
}

/* TaskCard 子组件 */
function TaskCard({
  task,
  selected,
  onClick,
  showProgress,
}: {
  task: ImportTaskItem
  selected: boolean
  onClick: () => void
  showProgress?: boolean
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`w-full rounded-xl border p-3 text-left transition-all ${
        selected
          ? "border-ring/70 bg-ring/5"
          : "bg-content1/55 hover:border-default-500/40"
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 space-y-0.5">
          <code className="text-[0.6rem] text-default-500 break-all">{task.task_id}</code>
          <div className="text-xs font-medium">{task.task_kind || task.mode || "-"}</div>
        </div>
        {statusBadge(task.status || "")}
      </div>
      {showProgress && (
        <>
          <div className="mt-1.5 flex items-center justify-between text-[0.6rem] text-default-500">
            <span>{task.current_step || "-"}</span>
            <span>{formatProgress(task.progress)}</span>
          </div>
          <div className="mt-1 h-1 w-full rounded-full bg-secondary overflow-hidden">
            <div
              className="h-full rounded-full bg-chart-3 transition-all duration-300"
              style={{ width: `${Math.min(100, Math.max(0, Number(task.progress ?? 0) * 100))}%` }}
            />
          </div>
        </>
      )}
    </button>
  )
}
