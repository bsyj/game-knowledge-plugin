import { useCallback, useEffect, useMemo, useState } from "react"
import { AlertCircle, AlertTriangle, ChevronDown, ChevronUp, Info, Megaphone, X } from "lucide-react"
import { cn } from "@/lib/utils"
import { fetchActiveAnnouncements, type Announcement, type AnnouncementSeverity } from "@/lib/api"

const STORAGE_KEY = "gk-webui-dismissed-announcements"

interface Props {
  /** 跳转到完整公告页（点击 Banner 标题/「查看全部」时调用）。 */
  onJump?: () => void
}

function severityIcon(severity: AnnouncementSeverity) {
  if (severity === "critical") return AlertCircle
  if (severity === "warning") return AlertTriangle
  return Info
}

function severityClass(severity: AnnouncementSeverity): string {
  if (severity === "critical") return "border-red-400/50 bg-red-500/12 text-red-700 dark:text-red-200"
  if (severity === "warning") return "border-amber-400/50 bg-amber-400/12 text-amber-700 dark:text-amber-200"
  return "border-sky-400/40 bg-sky-500/12 text-sky-700 dark:text-sky-200"
}

function readDismissed(): Set<number> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return new Set()
    const parsed = JSON.parse(raw)
    if (Array.isArray(parsed)) return new Set(parsed.filter((value: unknown) => typeof value === "number"))
  } catch {
    /* noop */
  }
  return new Set()
}

function writeDismissed(set: Set<number>): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(Array.from(set)))
  } catch {
    /* noop */
  }
}

export default function AnnouncementBanner({ onJump }: Props) {
  const [items, setItems] = useState<Announcement[]>([])
  const [dismissed, setDismissed] = useState<Set<number>>(() => readDismissed())
  const [collapsed, setCollapsed] = useState(false)

  const load = useCallback(async () => {
    try {
      const data = await fetchActiveAnnouncements(5)
      setItems(data.items || [])
    } catch {
      // 公告获取失败不阻断主流程
    }
  }, [])

  useEffect(() => {
    load()
    const timer = setInterval(load, 60_000)
    return () => clearInterval(timer)
  }, [load])

  const visibleItems = useMemo(
    () => items.filter((item) => !dismissed.has(item.id)),
    [items, dismissed],
  )

  if (visibleItems.length === 0) return null

  const dismiss = (id: number) => {
    setDismissed((prev) => {
      const next = new Set(prev)
      next.add(id)
      writeDismissed(next)
      return next
    })
  }

  const primary = visibleItems[0]
  const rest = visibleItems.slice(1)
  const Icon = severityIcon(primary.severity)

  return (
    <div className="mb-3 space-y-2">
      <div className={cn("flex items-start gap-2 rounded-2xl border px-3 py-2.5", severityClass(primary.severity))}>
        <Icon className="mt-0.5 h-4 w-4 shrink-0" />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={onJump}
              className="text-sm font-semibold underline-offset-2 hover:underline"
              title="查看公告详情"
            >
              {primary.title || "（无标题）"}
            </button>
            <span className="text-[10px] text-current/70">
              {primary.author_nickname || "管理员"}
            </span>
            {rest.length > 0 && (
              <button
                type="button"
                onClick={() => setCollapsed((value) => !value)}
                className="ml-auto inline-flex items-center gap-1 rounded-full bg-white/30 px-2 py-0.5 text-[10px] font-medium text-current dark:bg-black/20"
              >
                {collapsed ? <ChevronDown className="h-3 w-3" /> : <ChevronUp className="h-3 w-3" />}
                还有 {rest.length} 条
              </button>
            )}
          </div>
          <p className="mt-1 line-clamp-3 whitespace-pre-wrap text-xs leading-relaxed">
            {primary.content}
          </p>
          <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[10px] text-current/70">
            <Megaphone className="h-3 w-3" />
            <button type="button" onClick={onJump} className="hover:underline">查看全部公告</button>
          </div>
        </div>
        <button
          type="button"
          onClick={() => dismiss(primary.id)}
          className="ml-1 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-current/80 hover:bg-white/30 dark:hover:bg-black/30"
          aria-label="关闭公告"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>
      {!collapsed && rest.length > 0 && (
        <div className="space-y-2">
          {rest.map((item) => {
            const RestIcon = severityIcon(item.severity)
            return (
              <div
                key={item.id}
                className={cn("flex items-start gap-2 rounded-2xl border px-3 py-2", severityClass(item.severity))}
              >
                <RestIcon className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <div className="min-w-0 flex-1">
                  <button
                    type="button"
                    onClick={onJump}
                    className="text-xs font-semibold underline-offset-2 hover:underline"
                  >
                    {item.title || "（无标题）"}
                  </button>
                  <p className="mt-0.5 line-clamp-2 whitespace-pre-wrap text-[11px] leading-relaxed">
                    {item.content}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => dismiss(item.id)}
                  className="ml-1 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-current/80 hover:bg-white/30 dark:hover:bg-black/30"
                  aria-label="关闭公告"
                >
                  <X className="h-3 w-3" />
                </button>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
