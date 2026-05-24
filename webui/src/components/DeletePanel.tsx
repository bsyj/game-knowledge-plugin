import { useEffect, useState, useCallback } from "react"
import { RefreshCw, Trash2, Search, AlertTriangle, RotateCcw, ChevronLeft, ChevronRight } from "lucide-react"
import {
  previewDelete,
  executeDelete,
  restoreDelete,
  fetchDeleteOperations,
} from "@/lib/api"
import { useToast } from "@/components/Toast"
import Card from "@/components/Card"
import Button from "@/components/Button"
import Loading from "@/components/Loading"

type DeleteMode = "entity" | "relation" | "paragraph" | "source" | "mixed"

const DELETE_MODES: { key: DeleteMode; label: string }[] = [
  { key: "entity", label: "实体删除" },
  { key: "relation", label: "关系删除" },
  { key: "paragraph", label: "段落删除" },
  { key: "source", label: "来源删除" },
  { key: "mixed", label: "混合删除" },
]

interface DeletePreview {
  mode?: string
  item_count?: number
  counts?: { entities?: number; relations?: number; paragraphs?: number; sources?: number }
  sources?: string[]
  items?: Array<{
    item_type?: string
    item_hash?: string
    item_key?: string
    label?: string
    preview?: string
    source?: string
  }>
}

interface DeleteOperation {
  operation_id?: string
  mode?: string
  status?: string
  created_at?: number | string
  deleted_entity_count?: number
  deleted_relation_count?: number
  deleted_paragraph_count?: number
  deleted_source_count?: number
  selector?: Record<string, unknown>
}

const ITEMS_PER_PAGE = 10
const FULL_DELETE_CONFIRM_TEXT = "确认全量删除"

export default function DeletePanel() {
  const { toast } = useToast()
  const [mode, setMode] = useState<DeleteMode>("mixed")
  const [query, setQuery] = useState("")
  const [preview, setPreview] = useState<DeletePreview | null>(null)
  const [result, setResult] = useState<Record<string, unknown> | null>(null)
  const [loadingPreview, setLoadingPreview] = useState(false)
  const [executing, setExecuting] = useState(false)
  const [operations, setOperations] = useState<DeleteOperation[]>([])
  const [loadingOps, setLoadingOps] = useState(false)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [confirmText, setConfirmText] = useState("")
  const [itemPage, setItemPage] = useState(1)
  const [itemSearch, setItemSearch] = useState("")

  const loadOps = useCallback(async () => {
    setLoadingOps(true)
    try {
      const data = await fetchDeleteOperations(50)
      const od = data as { items?: DeleteOperation[]; success?: boolean }
      setOperations((od.items || []) as DeleteOperation[])
    } catch {
      toast("加载操作历史失败", "error")
    } finally {
      setLoadingOps(false)
    }
  }, [toast])

  useEffect(() => { loadOps() }, [loadOps])

  const handlePreview = async () => {
    setLoadingPreview(true)
    setPreview(null)
    setResult(null)
    setConfirmOpen(false)
    setConfirmText("")
    setItemPage(1)
    setItemSearch("")
    try {
      const selector = query.trim() ? { query: query.trim() } : {}
      const data = await previewDelete(mode, selector)
      setPreview(data as DeletePreview)
    } catch {
      toast("预览失败", "error")
    } finally {
      setLoadingPreview(false)
    }
  }

  const handleExecute = async () => {
    if (!fullDeleteConfirmed) {
      toast(`请输入「${FULL_DELETE_CONFIRM_TEXT}」后再执行全量删除`, "error")
      return
    }
    setExecuting(true)
    try {
      const selector = query.trim() ? { query: query.trim() } : {}
      const data = await executeDelete(mode, selector)
      setResult(data as Record<string, unknown>)
      setConfirmOpen(false)
      setConfirmText("")
      if ((data as Record<string, unknown>).success) {
        toast("删除成功", "success")
        loadOps()
      } else {
        toast("删除执行失败", "error")
      }
    } catch {
      toast("删除执行失败", "error")
    } finally {
      setExecuting(false)
    }
  }

  const handleRestore = async (operationId: string) => {
    try {
      await restoreDelete(operationId)
      toast("已恢复", "success")
      loadOps()
    } catch {
      toast("恢复失败", "error")
    }
  }

  const filteredItems = (preview?.items || []).filter((item) => {
    if (!itemSearch.trim()) return true
    const kw = itemSearch.trim().toLowerCase()
    return [item.item_type, item.item_hash, item.item_key, item.label, item.preview, item.source]
      .map((v) => String(v ?? "").toLowerCase())
      .some((v) => v.includes(kw))
  })
  const totalPages = Math.max(1, Math.ceil(filteredItems.length / ITEMS_PER_PAGE))
  const pagedItems = filteredItems.slice((itemPage - 1) * ITEMS_PER_PAGE, itemPage * ITEMS_PER_PAGE)
  const isFullDelete = !query.trim()
  const fullDeleteConfirmed = !isFullDelete || confirmText.trim() === FULL_DELETE_CONFIRM_TEXT

  const countBadges = [
    { key: "entities", label: "实体", value: Number(preview?.counts?.entities ?? 0) },
    { key: "relations", label: "关系", value: Number(preview?.counts?.relations ?? 0) },
    { key: "paragraphs", label: "段落", value: Number(preview?.counts?.paragraphs ?? 0) },
    { key: "sources", label: "来源", value: Number(preview?.counts?.sources ?? 0) },
  ].filter((c) => c.value > 0)

  return (
    <div className="space-y-5">
      {/* 删除操作区 */}
      <Card
        title="删除管理"
        actions={
          <Button variant="outline" size="sm" onClick={loadOps}>
            <RefreshCw className="h-3 w-3" />刷新
          </Button>
        }
      >
        <div className="space-y-4">
          {/* 模式选择 */}
          <div className="flex flex-wrap gap-1.5">
            {DELETE_MODES.map((m) => (
              <button
                key={m.key}
                onClick={() => setMode(m.key)}
                className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                  mode === m.key
                    ? "bg-gradient-to-r from-destructive to-destructive/80 text-destructive-foreground shadow-sm"
                    : "border border-white/10 text-default-500 hover:bg-accent hover:text-accent-foreground"
                }`}
              >
                {m.label}
              </button>
            ))}
          </div>

          {/* 查询输入 */}
          <div className="flex gap-2">
            <div className="relative flex-1">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-default-500" />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={mode === "source" ? "输入来源名（留空删除全部）" : "输入实体名/哈希/关键词（留空=全量）"}
                className="w-full h-9 rounded-xl border border-white/10 bg-content1/45 pl-8 pr-3 text-xs text-default-900 placeholder:text-default-500/60 focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>
            <Button variant="outline" onClick={handlePreview} disabled={loadingPreview}>
              {loadingPreview ? "预览中..." : "预览"}
            </Button>
          </div>

          {/* 预览结果 */}
          {preview && (
            <div className="rounded-xl border border-white/10 bg-content1/45 p-4 space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="inline-flex items-center rounded-full bg-destructive/20 px-2.5 py-0.5 text-[0.65rem] font-semibold text-destructive">
                  {DELETE_MODES.find((m) => m.key === (preview.mode || mode))?.label || preview.mode || mode}
                </span>
                <span className="inline-flex items-center rounded-full bg-secondary px-2.5 py-0.5 text-[0.65rem] font-semibold text-secondary-foreground">
                  预览项 {preview.item_count ?? filteredItems.length}
                </span>
                {countBadges.map((c) => (
                  <span key={c.key} className="inline-flex items-center rounded-full border border-white/10 px-2.5 py-0.5 text-[0.65rem] font-semibold text-default-500">
                    {c.label} {c.value}
                  </span>
                ))}
              </div>

              {(preview.sources || []).length > 0 && (
                <div className="text-xs text-default-500">
                  关联来源：{(preview.sources || []).join("、")}
                </div>
              )}

              {/* 明细列表 */}
              {filteredItems.length > 0 && (
                <div className="space-y-2">
                  <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                      <span className="text-sm font-semibold">本次将删除的对象</span>
                      <span className="ml-2 text-xs text-default-500">
                        第 {itemPage}/{totalPages} 页 · 共 {filteredItems.length} 项
                      </span>
                    </div>
                    <div className="relative">
                      <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3 w-3 -translate-y-1/2 text-default-500" />
                      <input
                        value={itemSearch}
                        onChange={(e) => { setItemSearch(e.target.value); setItemPage(1) }}
                        placeholder="搜索类型/hash/key/source..."
                        className="h-7 w-52 rounded-md border border-white/10 bg-content1/45 pl-7 pr-2 text-[0.65rem] text-default-900 placeholder:text-default-500/60 focus:outline-none focus:ring-1 focus:ring-primary"
                      />
                    </div>
                  </div>

                  <div className="max-h-[400px] overflow-y-auto space-y-1.5 rounded-xl border border-white/10 bg-default-100/30 p-3">
                    {pagedItems.map((item, idx) => (
                      <div key={`${item.item_type}:${item.item_hash}:${idx}`} className="rounded-md border border-white/10 bg-content1/45 p-2.5">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <span className="inline-flex items-center rounded border border-white/10 px-1.5 py-0.5 text-[0.6rem] font-medium text-default-500">
                            {item.item_type || "unknown"}
                          </span>
                          {item.source && (
                            <span className="inline-flex items-center rounded bg-secondary px-1.5 py-0.5 text-[0.6rem] font-medium text-secondary-foreground">
                              {item.source}
                            </span>
                          )}
                        </div>
                        <div className="mt-1.5 text-xs font-medium text-default-900 break-words">
                          {item.label || item.item_key || item.item_hash || "-"}
                        </div>
                        {item.preview && (
                          <div className="mt-1 text-[0.65rem] text-default-500 break-words">{item.preview}</div>
                        )}
                        <code className="mt-1.5 block break-all text-[0.6rem] text-default-500">
                          {item.item_hash || item.item_key || ""}
                        </code>
                      </div>
                    ))}
                  </div>

                  {totalPages > 1 && (
                    <div className="flex items-center justify-between">
                      <Button variant="outline" size="sm" disabled={itemPage <= 1} onClick={() => setItemPage((p) => p - 1)}>
                        <ChevronLeft className="h-3 w-3" />上一页
                      </Button>
                      <span className="text-xs text-default-500">第 {itemPage} / {totalPages} 页</span>
                      <Button variant="outline" size="sm" disabled={itemPage >= totalPages} onClick={() => setItemPage((p) => p + 1)}>
                        下一页<ChevronRight className="h-3 w-3" />
                      </Button>
                    </div>
                  )}
                </div>
              )}

              <Button
                variant="destructive"
                onClick={() => { setConfirmText(""); setConfirmOpen(true) }}
                disabled={executing || filteredItems.length === 0}
              >
                <Trash2 className="h-4 w-4" />{executing ? "执行中..." : "确认删除"}
              </Button>
            </div>
          )}

          {/* 确认对话框 */}
          {confirmOpen && (
            <div className="rounded-xl border border-destructive/40 bg-destructive/10 p-4 space-y-3">
              <div className="flex items-center gap-2">
                <AlertTriangle className="h-5 w-5 text-destructive" />
                <span className="text-sm font-semibold text-destructive">确认删除操作</span>
              </div>
              <p className="text-xs text-default-500">
                此操作不可撤销。将删除模式为 <strong>{DELETE_MODES.find((m) => m.key === mode)?.label}</strong> 的
                {preview ? ` ${preview.item_count ?? filteredItems.length} 个对象` : ""}，
                包括 {countBadges.length > 0 ? countBadges.map((c) => `${c.label} ${c.value}`).join("、") : "所有匹配项"}。
              </p>
              {isFullDelete && (
                <div className="space-y-2 rounded-lg border border-destructive/30 bg-content1/45 p-3">
                  <p className="text-xs font-semibold text-destructive">
                    当前查询为空，会执行全量删除。请输入「{FULL_DELETE_CONFIRM_TEXT}」继续。
                  </p>
                  <input
                    value={confirmText}
                    onChange={(e) => setConfirmText(e.target.value)}
                    placeholder={FULL_DELETE_CONFIRM_TEXT}
                    className="h-9 w-full rounded-lg border border-destructive/30 bg-background px-3 text-xs text-default-900 placeholder:text-default-500/60 focus:outline-none focus:ring-1 focus:ring-destructive"
                  />
                </div>
              )}
              <div className="flex gap-2">
                <Button variant="destructive" size="sm" onClick={handleExecute} disabled={executing || !fullDeleteConfirmed}>
                  {executing ? "执行中..." : "确认删除"}
                </Button>
                <Button variant="outline" size="sm" onClick={() => { setConfirmOpen(false); setConfirmText("") }}>取消</Button>
              </div>
            </div>
          )}

          {/* 执行结果 */}
          {result && (
            <div className={`rounded-xl border p-4 ${(result as Record<string, unknown>).success ? "border-chart-2/40 bg-chart-2/10" : "border-destructive/40 bg-destructive/10"}`}>
              <p className="text-sm font-semibold">{(result as Record<string, unknown>).success ? "删除成功" : "删除失败"}</p>
              {(result as Record<string, unknown>).success ? (
                <div className="mt-1 text-xs text-default-500">
                  操作ID: <code>{String((result as Record<string, unknown>).operation_id ?? "-")}</code>
                  {(result as Record<string, unknown>).deleted_entity_count != null && ` · 实体 ${(result as Record<string, unknown>).deleted_entity_count}`}
                  {(result as Record<string, unknown>).deleted_relation_count != null && ` · 关系 ${(result as Record<string, unknown>).deleted_relation_count}`}
                  {(result as Record<string, unknown>).deleted_paragraph_count != null && ` · 段落 ${(result as Record<string, unknown>).deleted_paragraph_count}`}
                  {(result as Record<string, unknown>).deleted_source_count != null && ` · 来源 ${(result as Record<string, unknown>).deleted_source_count}`}
                </div>
              ) : null}
            </div>
          )}
        </div>
      </Card>

      {/* 操作历史 */}
      <Card title="删除历史">
        {loadingOps ? <Loading />
        : operations.length === 0 ? (
          <p className="text-sm text-default-500">暂无删除操作记录</p>
        ) : (
          <div className="space-y-2">
            {operations.map((op) => (
              <div key={op.operation_id || String(op.created_at)} className="rounded-xl border border-white/10 bg-content1/45 p-3">
                <div className="flex items-center justify-between flex-wrap gap-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[0.65rem] font-semibold ${
                      op.status === "restored" ? "bg-chart-2/30 text-chart-2" : "bg-default-100/60 text-default-500"
                    }`}>
                      {op.status === "restored" ? "已恢复" : op.status || "已执行"}
                    </span>
                    <span className="text-[0.65rem] text-default-500">
                      {DELETE_MODES.find((m) => m.key === op.mode)?.label || op.mode || "未知"}
                    </span>
                    <code className="text-[0.6rem] text-default-500 truncate max-w-[100px]">{op.operation_id || "-"}</code>
                  </div>
                  <div className="flex items-center gap-1.5 text-[0.6rem] text-default-500">
                    {op.deleted_entity_count != null && <span>实体 {op.deleted_entity_count}</span>}
                    {op.deleted_relation_count != null && <span>· 关系 {op.deleted_relation_count}</span>}
                    {op.deleted_paragraph_count != null && <span>· 段落 {op.deleted_paragraph_count}</span>}
                    {op.deleted_source_count != null && <span>· 来源 {op.deleted_source_count}</span>}
                    {op.status !== "restored" && (
                      <Button variant="ghost" size="sm" onClick={() => handleRestore(op.operation_id!)}>
                        <RotateCcw className="h-3 w-3" />恢复
                      </Button>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  )
}
