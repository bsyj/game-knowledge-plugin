import { useEffect, useState } from "react"
import { Award, BadgeCheck, Clock3, Flame, RefreshCw, Save, Sparkles, Trophy, UserRound } from "lucide-react"
import { changePassword, fetchMyHistory, setAuthToken, updateProfile, type AuthUser } from "@/lib/api"
import Card from "@/components/Card"
import Button from "@/components/Button"
import { useToast } from "@/components/Toast"
import { formatDate, truncate } from "@/lib/utils"

interface HistoryItem {
  id: number
  card_id?: number
  base_card_id?: number
  action?: string
  actor_name?: string
  created_at?: number
  after?: Record<string, unknown>
}

interface ActivityStats {
  edited_total?: number
  updated_total?: number
  revision_total?: number
  created_from_search_total?: number
  reviewed_total?: number
  approved_total?: number
  rejected_total?: number
  pending_own_edits?: number
}

const ACTION_LABEL: Record<string, string> = {
  update: "更新卡片",
  revision: "提交修订",
  create_from_search: "检索修订",
}

const INPUT = "h-8 rounded-md border border-white/10 bg-content1/45 px-2 text-xs outline-none transition-colors focus:border-primary"

const STAT_ITEMS: Array<{ key: keyof ActivityStats; label: string; tone: string }> = [
  { key: "edited_total", label: "修改知识", tone: "text-primary" },
  { key: "revision_total", label: "提交修订", tone: "text-chart-4" },
  { key: "updated_total", label: "直接更新", tone: "text-chart-2" },
  { key: "created_from_search_total", label: "检索生成", tone: "text-chart-5" },
  { key: "reviewed_total", label: "审核处理", tone: "text-warning" },
  { key: "approved_total", label: "审核通过", tone: "text-success" },
  { key: "rejected_total", label: "审核拒绝", tone: "text-destructive" },
  { key: "pending_own_edits", label: "待审修改", tone: "text-default-500" },
]

function achievements(stats: ActivityStats) {
  const edited = stats.edited_total || 0
  const reviewed = stats.reviewed_total || 0
  const approved = stats.approved_total || 0
  const revisions = stats.revision_total || 0
  return [
    { title: "第一笔墨水", desc: "完成 1 次知识修改", unlocked: edited >= 1, icon: Sparkles },
    { title: "修订工匠", desc: "提交 5 次修订", unlocked: revisions >= 5, icon: Award },
    { title: "知识锻造师", desc: "累计修改 20 条", unlocked: edited >= 20, icon: Flame },
    { title: "把关人", desc: "审核 10 条卡片", unlocked: reviewed >= 10, icon: BadgeCheck },
    { title: "绿灯大师", desc: "通过 20 条卡片", unlocked: approved >= 20, icon: Trophy },
  ]
}

export default function ProfilePanel({ user, onUserChange }: { user: AuthUser; onUserChange: (user: AuthUser) => void }) {
  const { toast } = useToast()
  const [history, setHistory] = useState<HistoryItem[]>([])
  const [stats, setStats] = useState<ActivityStats>({})
  const [loading, setLoading] = useState(false)
  const [displayName, setDisplayName] = useState(user.display_name || "")
  const [passwordForm, setPasswordForm] = useState({ current_password: "", new_password: "" })

  const load = async () => {
    setLoading(true)
    try {
      const data = await fetchMyHistory(80) as { history?: HistoryItem[]; stats?: ActivityStats }
      setHistory(Array.isArray(data.history) ? data.history : [])
      setStats(data.stats || {})
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [])

  const saveProfile = async () => {
    try {
      const result = await updateProfile({ display_name: displayName })
      onUserChange(result.user)
      toast("个人资料已保存", "success")
    } catch {
      toast("保存失败", "error")
    }
  }

  const savePassword = async () => {
    if (!passwordForm.current_password || !passwordForm.new_password) return
    try {
      const result = await changePassword(passwordForm)
      setAuthToken(result.token)
      onUserChange(result.user)
      setPasswordForm({ current_password: "", new_password: "" })
      toast("密码已更新，旧会话已失效", "success")
    } catch {
      toast("修改密码失败", "error")
    }
  }

  return (
    <div className="grid gap-4 xl:grid-cols-[22rem_minmax(0,1fr)]">
      <Card title="个人中心">
        <div className="flex items-center gap-3">
          <div className="grid h-12 w-12 place-items-center rounded-2xl bg-primary/15 text-primary">
            <UserRound className="h-5 w-5" />
          </div>
          <div className="min-w-0">
            <div className="text-base font-semibold">{user.display_name || user.username}</div>
            <div className="text-xs text-default-500">@{user.username}</div>
          </div>
        </div>
        <div className="mt-4 flex flex-wrap gap-1.5">
          {(user.groups || []).map((group) => (
            <span key={group.id} className="rounded-md bg-default-100/70 px-2 py-1 text-xs text-default-700">
              {group.id}
            </span>
          ))}
        </div>
        <div className="mt-4 rounded-xl border border-white/10 bg-content1/35 p-3 text-xs text-default-500">
          <div>最近登录：{formatDate(user.last_login_at)}</div>
          {user.last_login_ip && <div className="mt-1">登录 IP：{user.last_login_ip}</div>}
          <div className="mt-1">Token 版本：{user.token_version || 1}</div>
        </div>
        <div className="mt-4 grid gap-2">
          <label className="grid gap-1 text-xs text-default-500">
            昵称
            <input className={INPUT} value={displayName} onChange={(event) => setDisplayName(event.target.value)} />
          </label>
          <Button size="sm" variant="outline" onClick={saveProfile}><Save className="h-3 w-3" />保存昵称</Button>
        </div>
        <div className="mt-4 grid gap-2 rounded-xl border border-white/10 bg-content1/25 p-3">
          <div className="text-xs font-semibold text-default-700">修改密码</div>
          <input className={INPUT} type="password" placeholder="当前密码" value={passwordForm.current_password} onChange={(event) => setPasswordForm((prev) => ({ ...prev, current_password: event.target.value }))} />
          <input className={INPUT} type="password" placeholder="新密码，8-128 位" value={passwordForm.new_password} onChange={(event) => setPasswordForm((prev) => ({ ...prev, new_password: event.target.value }))} />
          <Button size="sm" onClick={savePassword} disabled={!passwordForm.current_password || !passwordForm.new_password}>更新密码</Button>
        </div>
      </Card>

      <div className="space-y-4">
        <Card
          title="个人统计"
          actions={
            <Button variant="outline" size="sm" onClick={load} disabled={loading}>
              <RefreshCw className={`h-3 w-3 ${loading ? "animate-spin" : ""}`} />刷新
            </Button>
          }
        >
          <div className="grid gap-2 sm:grid-cols-4">
            {STAT_ITEMS.map((item) => (
              <div key={item.key} className="rounded-xl border border-white/10 bg-content1/45 p-3">
                <div className="text-xs text-default-500">{item.label}</div>
                <div className={`mt-1 text-2xl font-semibold ${item.tone}`}>{stats[item.key] || 0}</div>
              </div>
            ))}
          </div>
        </Card>

        <Card title="成就彩蛋">
          <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
            {achievements(stats).map((item) => {
              const Icon = item.icon
              return (
                <div
                  key={item.title}
                  className={`rounded-xl border p-3 transition-colors ${item.unlocked ? "border-primary/35 bg-primary/10 text-default-900" : "border-white/10 bg-content1/35 text-default-500"}`}
                >
                  <div className="flex items-center gap-2">
                    <div className={`grid h-8 w-8 place-items-center rounded-xl ${item.unlocked ? "bg-primary text-primary-foreground" : "bg-default-100/60"}`}>
                      <Icon className="h-4 w-4" />
                    </div>
                    <div className="min-w-0">
                      <div className="text-sm font-semibold">{item.unlocked ? item.title : "未解锁"}</div>
                      <div className="text-xs text-default-500">{item.desc}</div>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </Card>

        <Card title="编辑历史">
          {history.length === 0 ? (
            <div className="flex min-h-52 items-center justify-center text-sm text-default-500">暂无编辑记录</div>
          ) : (
            <div className="space-y-2">
              {history.map((item) => {
                const after = item.after || {}
                const title = String(after.title || after.question || `卡片 ${item.card_id || "-"}`)
                return (
                  <div key={item.id} className="rounded-xl border border-white/10 bg-content1/45 p-3">
                    <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
                      <span className="inline-flex items-center gap-1 rounded-md bg-primary/15 px-2 py-0.5 text-[0.68rem] font-semibold text-primary">
                        <Clock3 className="h-3 w-3" />{ACTION_LABEL[item.action || ""] || item.action || "操作"}
                      </span>
                      <span className="text-[0.68rem] text-default-500">{formatDate(item.created_at)}</span>
                    </div>
                    <div className="text-sm font-medium">{truncate(title, 90)}</div>
                    <div className="mt-1 text-xs text-default-500">
                      卡片 #{item.card_id || "-"}{item.base_card_id ? ` · 原卡片 #${item.base_card_id}` : ""}
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}
