import { useCallback, useEffect, useMemo, useState } from "react"
import { createPortal } from "react-dom"
import {
  MessageSquareQuote,
  Plus,
  Trash2,
  CornerDownRight,
  Loader2,
  Send,
  CheckCircle2,
  RefreshCw,
  Reply,
  X,
  Megaphone,
} from "lucide-react"
import Card from "@/components/Card"
import Button from "@/components/Button"
import { useToast } from "@/components/Toast"
import {
  createBoardThread,
  deleteBoardPost,
  deleteBoardThread,
  fetchBoardThread,
  fetchBoardThreads,
  hasPermission,
  replyBoardThread,
  resolveBoardThread,
  type AuthUser,
  type BoardPost,
  type BoardThread,
  type BoardThreadStatus,
} from "@/lib/api"
import { cn } from "@/lib/utils"

const STATUS_META: Record<BoardThreadStatus, { label: string; className: string }> = {
  open: { label: "待回复", className: "bg-sky-500/15 text-sky-600 dark:text-sky-300" },
  forwarded: { label: "已转发", className: "bg-violet-500/15 text-violet-600 dark:text-violet-300" },
  collecting: { label: "收集中", className: "bg-amber-500/15 text-amber-600 dark:text-amber-300" },
  resolved: { label: "已解决", className: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-300" },
  closed: { label: "已入库", className: "bg-default-300/20 text-default-600 dark:text-default-300" },
}

const FILTER_OPTIONS: { value: string; label: string }[] = [
  { value: "", label: "全部" },
  { value: "active", label: "进行中" },
  { value: "open", label: "待回复" },
  { value: "forwarded", label: "已转发到群" },
  { value: "collecting", label: "收集回答中" },
  { value: "done", label: "已结束" },
]

const BOARD_MODAL_CLASS =
  "border border-black/10 bg-white/95 text-slate-950 shadow-[0_24px_80px_rgb(15_23_42_/_0.24)] backdrop-blur-xl"
const BOARD_MODAL_FIELD_CLASS =
  "border border-slate-200 bg-white text-slate-950 placeholder:text-slate-400 shadow-sm focus:border-primary/60 focus:ring-2 focus:ring-primary/15"
const BOARD_MODAL_GHOST_BUTTON_CLASS =
  "text-slate-500 hover:bg-slate-100 hover:text-slate-950"

function formatTime(value: number | null | undefined): string {
  if (!value) return "—"
  const date = new Date(value * 1000)
  if (Number.isNaN(date.getTime())) return "—"
  return date.toLocaleString()
}

interface Props {
  user: AuthUser
}

export default function BoardPanel({ user }: Props) {
  const { toast } = useToast()
  const canResolve = hasPermission(user, "board.resolve")
  const canDeleteAny = hasPermission(user, "board.delete_any")

  const [threads, setThreads] = useState<BoardThread[]>([])
  const [filter, setFilter] = useState("active")
  const [loading, setLoading] = useState(false)
  const [activeThread, setActiveThread] = useState<BoardThread | null>(null)
  const [showCreate, setShowCreate] = useState(false)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const data = await fetchBoardThreads({ status: filter || undefined, limit: 100 })
      setThreads(data.items || [])
    } catch (err: any) {
      toast(err?.response?.data?.error || "加载留言失败", "error")
    } finally {
      setLoading(false)
    }
  }, [filter, toast])

  useEffect(() => { refresh() }, [refresh])

  const refreshThread = useCallback(async (threadId: number) => {
    try {
      const data = await fetchBoardThread(threadId)
      setActiveThread(data.item)
    } catch (err: any) {
      toast(err?.response?.data?.error || "加载主题失败", "error")
    }
  }, [toast])

  const handleOpen = async (thread: BoardThread) => {
    await refreshThread(thread.id)
  }

  const handleDeleteThread = async (thread: BoardThread) => {
    const canDelete = canDeleteAny || thread.author_id === user.id
    if (!canDelete) {
      toast("无权删除该留言", "error")
      return
    }
    if (!window.confirm(`确认删除主题「${thread.title}」？该操作不可恢复。`)) return
    try {
      await deleteBoardThread(thread.id)
      toast("已删除", "success")
      if (activeThread?.id === thread.id) setActiveThread(null)
      refresh()
    } catch (err: any) {
      toast(err?.response?.data?.error || "删除失败", "error")
    }
  }

  if (activeThread) {
    return (
      <ThreadDetail
        thread={activeThread}
        user={user}
        canResolve={canResolve}
        canDeleteAny={canDeleteAny}
        onBack={() => {
          setActiveThread(null)
          refresh()
        }}
        onRefresh={() => refreshThread(activeThread.id)}
      />
    )
  }

  return (
    <div className="space-y-4">
      <Card
        title={
          <div className="flex items-center gap-2">
            <MessageSquareQuote className="h-4 w-4" />
            <span>留言板</span>
            <span className="text-xs font-normal text-default-500">群友找不到知识时留言，其他人来回答</span>
          </div>
        }
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <select
              value={filter}
              onChange={(event) => setFilter(event.target.value)}
              className="napcat-input h-8 min-w-[7rem] rounded-full px-3 text-xs"
            >
              {FILTER_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
            <Button size="sm" variant="ghost" onClick={refresh} disabled={loading}>
              {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
              刷新
            </Button>
            <Button size="sm" onClick={() => setShowCreate(true)}>
              <Plus className="h-3.5 w-3.5" />
              发新留言
            </Button>
          </div>
        }
      >
        {threads.length === 0 ? (
          <p className="rounded-2xl border border-dashed border-default-200/70 bg-default-100/40 px-4 py-10 text-center text-sm text-default-500">
            还没有留言。
          </p>
        ) : (
          <div className="space-y-2">
            {threads.map((thread) => {
              const meta = STATUS_META[thread.status]
              const canDelete = canDeleteAny || thread.author_id === user.id
              return (
                <div
                  key={thread.id}
                  className="group flex flex-wrap items-center gap-3 rounded-2xl border border-default-200/40 bg-default-100/40 px-3 py-2.5 transition-colors hover:bg-default-100/70"
                >
                  <button
                    type="button"
                    onClick={() => handleOpen(thread)}
                    className="flex min-w-0 flex-1 items-center gap-3 text-left"
                  >
                    <span className={cn("inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold", meta.className)}>
                      {meta.label}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-semibold text-default-900">
                        {thread.title || "（无标题）"}
                      </span>
                      <span className="block truncate text-[11px] text-default-500">
                        {thread.author_nickname || "群友"} · 回复 {thread.reply_count}
                        {thread.forwarded_at ? <> · 已转发到群 {formatTime(thread.forwarded_at)}</> : null}
                        {" · "}
                        {formatTime(thread.last_reply_at || thread.created_at)}
                      </span>
                    </span>
                  </button>
                  {canDelete && (
                    <button
                      type="button"
                      onClick={() => handleDeleteThread(thread)}
                      className="inline-flex h-7 w-7 items-center justify-center rounded-full text-default-500 hover:text-red-500"
                      aria-label="删除主题"
                      title="删除主题"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </Card>

      {showCreate && (
        <CreateThreadDialog
          onClose={() => setShowCreate(false)}
          onCreated={async (thread) => {
            setShowCreate(false)
            await refresh()
            await refreshThread(thread.id)
          }}
        />
      )}
    </div>
  )
}

function ThreadDetail({
  thread,
  user,
  canResolve,
  canDeleteAny,
  onBack,
  onRefresh,
}: {
  thread: BoardThread
  user: AuthUser
  canResolve: boolean
  canDeleteAny: boolean
  onBack: () => void
  onRefresh: () => Promise<void> | void
}) {
  const { toast } = useToast()
  const meta = STATUS_META[thread.status]
  const posts = thread.posts || []
  const [replyContent, setReplyContent] = useState("")
  const [replyTo, setReplyTo] = useState<BoardPost | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [showResolve, setShowResolve] = useState(false)
  const isClosed = thread.status === "closed"

  const submitReply = async () => {
    const trimmed = replyContent.trim()
    if (!trimmed) {
      toast("回复内容不能为空", "error")
      return
    }
    setSubmitting(true)
    try {
      await replyBoardThread(thread.id, {
        content: trimmed,
        reply_to_post_id: replyTo?.id ?? null,
      })
      toast("回复已发送", "success")
      setReplyContent("")
      setReplyTo(null)
      await onRefresh()
    } catch (err: any) {
      toast(err?.response?.data?.error || "回复失败", "error")
    } finally {
      setSubmitting(false)
    }
  }

  const handleDeletePost = async (post: BoardPost) => {
    const canDelete = canDeleteAny || post.author_id === user.id
    if (!canDelete) {
      toast("无权删除该楼层", "error")
      return
    }
    if (!window.confirm("确认删除该楼层？")) return
    try {
      await deleteBoardPost(post.id)
      toast("已删除", "success")
      if (replyTo?.id === post.id) setReplyTo(null)
      await onRefresh()
    } catch (err: any) {
      toast(err?.response?.data?.error || "删除失败", "error")
    }
  }

  return (
    <div className="space-y-4">
      <Card
        title={
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onBack}
              className="inline-flex items-center gap-1 text-xs text-default-500 hover:text-default-900"
            >
              ← 返回列表
            </button>
            <span className={cn("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold", meta.className)}>
              {meta.label}
            </span>
            <span className="truncate text-base font-semibold">{thread.title}</span>
          </div>
        }
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Button size="sm" variant="ghost" onClick={() => onRefresh()}>
              <RefreshCw className="h-3.5 w-3.5" />
              刷新
            </Button>
            {canResolve && !isClosed && (
              <Button size="sm" variant="success" onClick={() => setShowResolve(true)}>
                <CheckCircle2 className="h-3.5 w-3.5" />
                标记已解决并入库
              </Button>
            )}
          </div>
        }
      >
        <p className="text-[11px] text-default-500">
          发起人 {thread.author_nickname || "群友"} · 创建于 {formatTime(thread.created_at)}
          {thread.forwarded_at ? <> · 已转发到群 {formatTime(thread.forwarded_at)}</> : null}
          {thread.resolved_at ? <> · 解决于 {formatTime(thread.resolved_at)}</> : null}
        </p>

        <div className="mt-3 space-y-2.5">
          {posts.map((post, index) => {
            const quotedPost = post.reply_to_post_id
              ? posts.find((item) => item.id === post.reply_to_post_id)
              : null
            const canDelete = canDeleteAny || post.author_id === user.id
            const isHead = index === 0
            return (
              <div
                key={post.id}
                className={cn(
                  "rounded-2xl border px-3 py-2.5",
                  isHead
                    ? "border-primary/30 bg-primary/5"
                    : post.source === "qq"
                      ? "border-amber-300/40 bg-amber-300/10"
                      : "border-default-200/40 bg-default-100/40",
                )}
              >
                <div className="flex flex-wrap items-center gap-2 text-[11px] text-default-500">
                  <span className="font-semibold text-default-900">
                    {post.author_nickname || (post.source === "qq" ? "QQ 群友" : "群友")}
                  </span>
                  {isHead && (
                    <span className="rounded-full bg-primary/20 px-1.5 py-0.5 text-[10px] text-primary-foreground/90">
                      提问
                    </span>
                  )}
                  {post.source === "qq" && (
                    <span className="rounded-full bg-amber-300/30 px-1.5 py-0.5 text-[10px] text-amber-700 dark:text-amber-300">
                      QQ 群
                    </span>
                  )}
                  <span>#{index + 1}</span>
                  <span>· {formatTime(post.created_at)}</span>
                  <span className="ml-auto flex items-center gap-1">
                    {!isHead && !isClosed && (
                      <button
                        type="button"
                        onClick={() => setReplyTo(post)}
                        className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] text-default-500 hover:text-default-900"
                        title="引用回复此楼"
                      >
                        <Reply className="h-3 w-3" />
                        引用
                      </button>
                    )}
                    {canDelete && (
                      <button
                        type="button"
                        onClick={() => handleDeletePost(post)}
                        className="inline-flex h-6 w-6 items-center justify-center rounded-full text-default-500 hover:text-red-500"
                        aria-label="删除楼层"
                      >
                        <Trash2 className="h-3 w-3" />
                      </button>
                    )}
                  </span>
                </div>
                {quotedPost && (
                  <div className="mt-1.5 flex items-start gap-1.5 rounded-xl border border-default-300/30 bg-default-100/40 px-2 py-1 text-[11px] text-default-500">
                    <CornerDownRight className="mt-0.5 h-3 w-3" />
                    <span className="line-clamp-2 break-words">
                      回复 {quotedPost.author_nickname || "群友"}：{quotedPost.content}
                    </span>
                  </div>
                )}
                <p className="mt-1.5 whitespace-pre-wrap break-words text-sm leading-relaxed text-default-900">
                  {post.content}
                </p>
              </div>
            )
          })}
        </div>

        {!isClosed && (
          <div className="mt-4 space-y-2 rounded-2xl border border-default-200/60 bg-default-100/40 p-3">
            {replyTo && (
              <div className="flex items-start justify-between gap-2 rounded-xl border border-default-300/40 bg-default-200/50 px-2 py-1 text-[11px] text-default-600">
                <span className="line-clamp-2 break-words">
                  引用 {replyTo.author_nickname || "群友"}：{replyTo.content}
                </span>
                <button
                  type="button"
                  onClick={() => setReplyTo(null)}
                  className="inline-flex h-5 w-5 items-center justify-center rounded-full hover:bg-default-300/40"
                  aria-label="取消引用"
                >
                  <X className="h-3 w-3" />
                </button>
              </div>
            )}
            <textarea
              className="napcat-input min-h-[80px] w-full rounded-xl px-3 py-2 text-sm"
              placeholder="写下你的回答或补充…"
              value={replyContent}
              onChange={(event) => setReplyContent(event.target.value)}
              maxLength={8000}
            />
            <div className="flex justify-end">
              <Button size="sm" onClick={submitReply} disabled={submitting}>
                {submitting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
                发送回复
              </Button>
            </div>
          </div>
        )}
      </Card>

      {showResolve && (
        <ResolveDialog
          thread={thread}
          onClose={() => setShowResolve(false)}
          onDone={async () => {
            setShowResolve(false)
            await onRefresh()
          }}
        />
      )}
    </div>
  )
}

function CreateThreadDialog({
  onClose,
  onCreated,
}: {
  onClose: () => void
  onCreated: (thread: BoardThread) => void
}) {
  const { toast } = useToast()
  const [title, setTitle] = useState("")
  const [content, setContent] = useState("")
  const [submitting, setSubmitting] = useState(false)

  const submit = async () => {
    if (!title.trim() || !content.trim()) {
      toast("标题和内容不能为空", "error")
      return
    }
    setSubmitting(true)
    try {
      const result = await createBoardThread({ title: title.trim(), content: content.trim() })
      toast("留言已发布", "success")
      onCreated(result.item)
    } catch (err: any) {
      toast(err?.response?.data?.error || "发布失败", "error")
    } finally {
      setSubmitting(false)
    }
  }

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-3 py-6 backdrop-blur-sm">
      <div className={cn("w-full max-w-lg overflow-y-auto rounded-2xl p-5", BOARD_MODAL_CLASS)}>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-base font-semibold">发起新留言</h2>
          <button type="button" onClick={onClose} className="text-sm text-slate-500 hover:text-slate-950">
            取消
          </button>
        </div>
        <div className="space-y-3">
          <div>
            <label className="mb-1 block text-xs text-slate-500">标题（一句话说明问题）</label>
            <input
              className={cn("napcat-input h-9 w-full rounded-xl px-3 text-sm", BOARD_MODAL_FIELD_CLASS)}
              value={title}
              maxLength={200}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="例如：xxx 怎么获取？"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-slate-500">详细描述</label>
            <textarea
              className={cn("napcat-input min-h-[120px] w-full rounded-xl px-3 py-2 text-sm", BOARD_MODAL_FIELD_CLASS)}
              value={content}
              maxLength={8000}
              onChange={(event) => setContent(event.target.value)}
              placeholder="把你遇到的情境写清楚，方便别人回答…"
            />
          </div>
          <p className="rounded-xl border border-amber-300/40 bg-amber-50 px-3 py-2 text-[11px] text-amber-700">
            <Megaphone className="mr-1 inline h-3 w-3" />
            若 2 天内无人回应，bot 会把问题转发到许可的 QQ 群求助；收到回答后自动入审核队列。
          </p>
        </div>
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={onClose} disabled={submitting} className={BOARD_MODAL_GHOST_BUTTON_CLASS}>取消</Button>
          <Button size="sm" onClick={submit} disabled={submitting}>
            {submitting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "发布"}
          </Button>
        </div>
      </div>
    </div>,
    document.body,
  )
}

function ResolveDialog({
  thread,
  onClose,
  onDone,
}: {
  thread: BoardThread
  onClose: () => void
  onDone: () => void | Promise<void>
}) {
  const { toast } = useToast()
  const posts = thread.posts || []
  const replyPosts = posts.slice(1)
  const [picked, setPicked] = useState<Set<number>>(() => new Set(replyPosts.map((post) => post.id)))
  const [submitting, setSubmitting] = useState(false)

  const togglePick = (postId: number) => {
    setPicked((prev) => {
      const next = new Set(prev)
      if (next.has(postId)) next.delete(postId)
      else next.add(postId)
      return next
    })
  }

  const submit = async () => {
    setSubmitting(true)
    try {
      const result = await resolveBoardThread(thread.id, { picked_post_ids: Array.from(picked) })
      if (result.success) {
        const submitted = result.submitted || 0
        if (submitted > 0) toast(`已入库 ${submitted} 张卡片，进入审核队列`, "success")
        else toast(result.note || "已标记为已解决（无卡片入库）", "info")
        await onDone()
      } else {
        toast(result.error || "入库失败", "error")
      }
    } catch (err: any) {
      toast(err?.response?.data?.error || "入库失败", "error")
    } finally {
      setSubmitting(false)
    }
  }

  const summary = useMemo(() => `已选中 ${picked.size} / ${replyPosts.length} 楼作为答案`, [picked.size, replyPosts.length])

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-3 py-6 backdrop-blur-sm">
      <div className={cn("flex max-h-[85vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl", BOARD_MODAL_CLASS)}>
        <div className="flex items-center justify-between border-b border-black/10 px-5 pb-3 pt-5">
          <h2 className="text-base font-semibold">标记已解决并入库</h2>
          <button type="button" onClick={onClose} className="text-sm text-slate-500 hover:text-slate-950">
            取消
          </button>
        </div>
        <p className="px-5 pt-3 text-xs text-slate-500">
          勾选哪些楼层作为答案；系统会把【提问 + 选中楼层】交给 game_knowledge 分析器生成卡片，进入待审核队列。{summary}。
        </p>
        <div className="my-3 flex-1 overflow-y-auto px-5">
          {replyPosts.length === 0 ? (
            <p className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 px-4 py-6 text-center text-xs text-slate-500">
              暂无可选答案楼层。直接确认会把主题标记为已解决（不产生卡片）。
            </p>
          ) : (
            <div className="space-y-2">
              {replyPosts.map((post, index) => (
                <label
                  key={post.id}
                  className={cn(
                    "flex cursor-pointer items-start gap-2 rounded-2xl border px-3 py-2 transition-colors",
                    picked.has(post.id)
                      ? "border-primary/45 bg-primary/10"
                      : "border-slate-200 bg-slate-50 hover:bg-slate-100",
                  )}
                >
                  <input
                    type="checkbox"
                    className="mt-1"
                    checked={picked.has(post.id)}
                    onChange={() => togglePick(post.id)}
                  />
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 text-[11px] text-slate-500">
                      <span className="font-semibold text-slate-950">
                        {post.author_nickname || (post.source === "qq" ? "QQ 群友" : "群友")}
                      </span>
                      {post.source === "qq" && (
                        <span className="rounded-full bg-amber-100 px-1.5 py-0.5 text-[10px] text-amber-700">QQ 群</span>
                      )}
                      <span>#{index + 2}</span>
                    </div>
                    <p className="mt-1 whitespace-pre-wrap break-words text-sm text-slate-950">
                      {post.content}
                    </p>
                  </div>
                </label>
              ))}
            </div>
          )}
        </div>
        <div className="flex items-center justify-end gap-2 border-t border-slate-200 px-5 py-3">
          <Button variant="ghost" size="sm" onClick={onClose} disabled={submitting} className={BOARD_MODAL_GHOST_BUTTON_CLASS}>取消</Button>
          <Button size="sm" variant="success" onClick={submit} disabled={submitting}>
            {submitting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CheckCircle2 className="h-3.5 w-3.5" />}
            确认入库
          </Button>
        </div>
      </div>
    </div>,
    document.body,
  )
}
