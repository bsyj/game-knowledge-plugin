import { useCallback, useEffect, useMemo, useState } from "react"
import { createPortal } from "react-dom"
import { Megaphone, Plus, Trash2, AlertTriangle, AlertCircle, Info, Pin, Loader2 } from "lucide-react"
import Card from "@/components/Card"
import Button from "@/components/Button"
import { useToast } from "@/components/Toast"
import {
  createAnnouncement,
  deleteAnnouncement,
  fetchAnnouncements,
  hasPermission,
  type Announcement,
  type AnnouncementCreatePayload,
  type AnnouncementSeverity,
  type AnnouncementStatus,
  type AuthUser,
} from "@/lib/api"
import { cn } from "@/lib/utils"

const SEVERITY_OPTIONS: { value: AnnouncementSeverity; label: string }[] = [
  { value: "info", label: "提示 info" },
  { value: "warning", label: "警告 warning" },
  { value: "critical", label: "严重 critical" },
]

const STATUS_OPTIONS: { value: AnnouncementStatus; label: string }[] = [
  { value: "published", label: "立即发布" },
  { value: "draft", label: "保存为草稿" },
]

const ANNOUNCEMENT_MODAL_CLASS =
  "border border-black/10 bg-white/95 text-slate-950 shadow-[0_24px_80px_rgb(15_23_42_/_0.24)] backdrop-blur-xl"
const ANNOUNCEMENT_MODAL_FIELD_CLASS =
  "border border-slate-200 bg-white text-slate-950 placeholder:text-slate-400 shadow-sm focus:border-primary/60 focus:ring-2 focus:ring-primary/15"
const ANNOUNCEMENT_MODAL_GHOST_BUTTON_CLASS =
  "text-slate-500 hover:bg-slate-100 hover:text-slate-950"

function formatTimestamp(value: number | null | undefined): string {
  if (!value) return "—"
  const date = new Date(value * 1000)
  if (Number.isNaN(date.getTime())) return "—"
  return date.toLocaleString()
}

function severityClass(severity: AnnouncementSeverity): string {
  if (severity === "critical") return "border-red-400/40 bg-red-500/10 text-red-600 dark:text-red-300"
  if (severity === "warning") return "border-amber-400/40 bg-amber-400/10 text-amber-600 dark:text-amber-300"
  return "border-sky-400/40 bg-sky-500/10 text-sky-600 dark:text-sky-300"
}

function severityIcon(severity: AnnouncementSeverity) {
  if (severity === "critical") return AlertCircle
  if (severity === "warning") return AlertTriangle
  return Info
}

function toUnixSeconds(value: string): number | null {
  if (!value) return null
  const time = new Date(value).getTime()
  if (Number.isNaN(time)) return null
  return time / 1000
}

interface Props {
  user: AuthUser
}

export default function AnnouncementsPanel({ user }: Props) {
  const { toast } = useToast()
  const canPublish = hasPermission(user, "announcement.publish")
  const canDelete = hasPermission(user, "announcement.delete")

  const [items, setItems] = useState<Announcement[]>([])
  const [loading, setLoading] = useState(false)
  const [filterStatus, setFilterStatus] = useState<"" | AnnouncementStatus>("")
  const [showCreate, setShowCreate] = useState(false)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const data = await fetchAnnouncements({ status: filterStatus || undefined, include_inactive: true, limit: 100 })
      setItems(data.items || [])
    } catch (err: any) {
      toast(err?.response?.data?.error || "加载公告失败", "error")
    } finally {
      setLoading(false)
    }
  }, [filterStatus, toast])

  useEffect(() => { refresh() }, [refresh])

  const handleDelete = async (id: number) => {
    if (!canDelete) {
      toast("无权删除公告", "error")
      return
    }
    if (!window.confirm("确认删除该公告？删除后无法恢复。")) return
    try {
      await deleteAnnouncement(id)
      toast("公告已删除", "success")
      refresh()
    } catch (err: any) {
      toast(err?.response?.data?.error || "删除失败", "error")
    }
  }

  const grouped = useMemo(() => {
    const pinned = items.filter((item) => item.pinned)
    const rest = items.filter((item) => !item.pinned)
    return { pinned, rest }
  }, [items])

  return (
    <div className="space-y-4">
      <Card
        title={
          <div className="flex items-center gap-2">
            <Megaphone className="h-4 w-4" />
            <span>公告</span>
          </div>
        }
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <select
              value={filterStatus}
              onChange={(event) => setFilterStatus(event.target.value as "" | AnnouncementStatus)}
              className="napcat-input h-8 min-w-[7rem] rounded-full px-3 text-xs"
            >
              <option value="">全部状态</option>
              <option value="published">已发布</option>
              <option value="draft">草稿</option>
            </select>
            <Button size="sm" variant="ghost" onClick={refresh} disabled={loading}>
              {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "刷新"}
            </Button>
            {canPublish && (
              <Button size="sm" onClick={() => setShowCreate(true)}>
                <Plus className="h-3.5 w-3.5" />
                发布公告
              </Button>
            )}
          </div>
        }
      >
        {items.length === 0 ? (
          <p className="rounded-2xl border border-dashed border-default-200/70 bg-default-100/40 px-4 py-10 text-center text-sm text-default-500">
            还没有公告。{canPublish ? "点击右上角「发布公告」开始。" : "等待管理员发布。"}
          </p>
        ) : (
          <div className="space-y-3">
            {grouped.pinned.length > 0 && (
              <AnnouncementGroup
                label="置顶"
                items={grouped.pinned}
                canDelete={canDelete}
                onDelete={handleDelete}
              />
            )}
            <AnnouncementGroup
              label={grouped.pinned.length > 0 ? "其他公告" : "公告列表"}
              items={grouped.rest}
              canDelete={canDelete}
              onDelete={handleDelete}
            />
          </div>
        )}
      </Card>

      {showCreate && canPublish && (
        <CreateAnnouncementDialog
          onClose={() => setShowCreate(false)}
          onCreated={() => {
            setShowCreate(false)
            refresh()
          }}
        />
      )}
    </div>
  )
}

function AnnouncementGroup({
  label,
  items,
  canDelete,
  onDelete,
}: {
  label: string
  items: Announcement[]
  canDelete: boolean
  onDelete: (id: number) => void
}) {
  if (items.length === 0) return null
  return (
    <div className="space-y-2">
      <p className="px-1 text-xs font-semibold text-default-500">{label}</p>
      <div className="space-y-2">
        {items.map((item) => (
          <AnnouncementCard key={item.id} item={item} canDelete={canDelete} onDelete={onDelete} />
        ))}
      </div>
    </div>
  )
}

function AnnouncementCard({
  item,
  canDelete,
  onDelete,
}: {
  item: Announcement
  canDelete: boolean
  onDelete: (id: number) => void
}) {
  const Icon = severityIcon(item.severity)
  return (
    <div className={cn("rounded-2xl border px-4 py-3 transition-colors", severityClass(item.severity))}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex items-start gap-2">
          <Icon className="mt-0.5 h-4 w-4 shrink-0" />
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-semibold">{item.title || "（无标题）"}</span>
              {item.pinned && (
                <span className="inline-flex items-center gap-1 rounded-full bg-white/40 px-1.5 py-0.5 text-[10px] dark:bg-black/30">
                  <Pin className="h-3 w-3" /> 置顶
                </span>
              )}
              {item.status === "draft" && (
                <span className="inline-flex items-center rounded-full bg-default-200/60 px-1.5 py-0.5 text-[10px] text-default-600 dark:text-default-300">
                  草稿
                </span>
              )}
            </div>
            <p className="mt-1 whitespace-pre-wrap break-words text-xs leading-relaxed text-default-800/90 dark:text-default-100/90">
              {item.content}
            </p>
            <p className="mt-2 text-[11px] text-default-500">
              {item.author_nickname || "管理员"} · {formatTimestamp(item.created_at)}
              {item.starts_at || item.ends_at ? (
                <> · 有效 {formatTimestamp(item.starts_at)} – {formatTimestamp(item.ends_at)}</>
              ) : null}
            </p>
          </div>
        </div>
        {canDelete && (
          <button
            type="button"
            onClick={() => onDelete(item.id)}
            className="inline-flex h-7 w-7 items-center justify-center rounded-full border border-white/40 text-current opacity-70 transition-opacity hover:opacity-100 dark:border-white/15"
            aria-label="删除公告"
            title="删除公告"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        )}
      </div>
    </div>
  )
}

function CreateAnnouncementDialog({
  onClose,
  onCreated,
}: {
  onClose: () => void
  onCreated: () => void
}) {
  const { toast } = useToast()
  const [title, setTitle] = useState("")
  const [content, setContent] = useState("")
  const [severity, setSeverity] = useState<AnnouncementSeverity>("info")
  const [pinned, setPinned] = useState(false)
  const [status, setStatus] = useState<AnnouncementStatus>("published")
  const [startsAt, setStartsAt] = useState("")
  const [endsAt, setEndsAt] = useState("")
  const [submitting, setSubmitting] = useState(false)

  const submit = async () => {
    if (!title.trim() || !content.trim()) {
      toast("标题和正文不能为空", "error")
      return
    }
    const payload: AnnouncementCreatePayload = {
      title: title.trim(),
      content: content.trim(),
      severity,
      pinned,
      status,
      starts_at: toUnixSeconds(startsAt),
      ends_at: toUnixSeconds(endsAt),
    }
    setSubmitting(true)
    try {
      await createAnnouncement(payload)
      toast("公告已发布", "success")
      onCreated()
    } catch (err: any) {
      toast(err?.response?.data?.error || "发布失败", "error")
    } finally {
      setSubmitting(false)
    }
  }

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-3 py-6 backdrop-blur-sm">
      <div className={cn("w-full max-w-lg overflow-y-auto rounded-2xl p-5", ANNOUNCEMENT_MODAL_CLASS)}>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-base font-semibold">发布公告</h2>
          <button type="button" onClick={onClose} className="text-sm text-slate-500 hover:text-slate-950">
            取消
          </button>
        </div>
        <div className="space-y-3">
          <div>
            <label className="mb-1 block text-xs text-slate-500">标题</label>
            <input
              className={cn("napcat-input h-9 w-full rounded-xl px-3 text-sm", ANNOUNCEMENT_MODAL_FIELD_CLASS)}
              value={title}
              maxLength={200}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="例如：本周三 21:00 维护"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-slate-500">正文（支持纯文本/换行）</label>
            <textarea
              className={cn("napcat-input min-h-[120px] w-full rounded-xl px-3 py-2 text-sm", ANNOUNCEMENT_MODAL_FIELD_CLASS)}
              value={content}
              maxLength={20000}
              onChange={(event) => setContent(event.target.value)}
              placeholder="详细说明…"
            />
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-xs text-slate-500">严重程度</label>
              <select
                className={cn("napcat-input h-9 w-full rounded-xl px-3 text-sm", ANNOUNCEMENT_MODAL_FIELD_CLASS)}
                value={severity}
                onChange={(event) => setSeverity(event.target.value as AnnouncementSeverity)}
              >
                {SEVERITY_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs text-slate-500">发布状态</label>
              <select
                className={cn("napcat-input h-9 w-full rounded-xl px-3 text-sm", ANNOUNCEMENT_MODAL_FIELD_CLASS)}
                value={status}
                onChange={(event) => setStatus(event.target.value as AnnouncementStatus)}
              >
                {STATUS_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs text-slate-500">生效时间（可空）</label>
              <input
                className={cn("napcat-input h-9 w-full rounded-xl px-3 text-sm", ANNOUNCEMENT_MODAL_FIELD_CLASS)}
                type="datetime-local"
                value={startsAt}
                onChange={(event) => setStartsAt(event.target.value)}
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-slate-500">失效时间（可空）</label>
              <input
                className={cn("napcat-input h-9 w-full rounded-xl px-3 text-sm", ANNOUNCEMENT_MODAL_FIELD_CLASS)}
                type="datetime-local"
                value={endsAt}
                onChange={(event) => setEndsAt(event.target.value)}
              />
            </div>
          </div>
          <label className="flex items-center gap-2 text-xs text-slate-600">
            <input type="checkbox" checked={pinned} onChange={(event) => setPinned(event.target.checked)} />
            置顶到 Banner（顶部高亮提示）
          </label>
        </div>
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={onClose} disabled={submitting} className={ANNOUNCEMENT_MODAL_GHOST_BUTTON_CLASS}>取消</Button>
          <Button size="sm" onClick={submit} disabled={submitting}>
            {submitting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "发布"}
          </Button>
        </div>
      </div>
    </div>,
    document.body,
  )
}
