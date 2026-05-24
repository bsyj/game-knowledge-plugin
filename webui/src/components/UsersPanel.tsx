import { useEffect, useState } from "react"
import { AlertTriangle, RefreshCw, Save, Trash2, UserPlus } from "lucide-react"
import {
  createUser,
  deleteUser,
  fetchAuthAudit,
  fetchUsers,
  updateUser,
  type AuthAuditEvent,
  type AuthGroup,
  type AuthUser,
} from "@/lib/api"
import Card from "@/components/Card"
import Button from "@/components/Button"
import { useToast } from "@/components/Toast"
import { formatDate } from "@/lib/utils"

const INPUT = "h-8 rounded-md border border-white/10 bg-content1/45 px-2 text-xs outline-none transition-colors focus:border-primary"

export default function UsersPanel() {
  const { toast } = useToast()
  const [users, setUsers] = useState<AuthUser[]>([])
  const [groups, setGroups] = useState<AuthGroup[]>([])
  const [audit, setAudit] = useState<AuthAuditEvent[]>([])
  const [loading, setLoading] = useState(false)
  const [ipFilter, setIpFilter] = useState("")
  const [form, setForm] = useState({ username: "", display_name: "", password: "", group_id: "viewer" })

  const load = async () => {
    setLoading(true)
    try {
      const params = ipFilter.trim() ? { ip: ipFilter.trim() } : {}
      const data = await fetchUsers(params)
      const auditData = await fetchAuthAudit(80, params)
      setUsers(data.users || [])
      setGroups(data.groups || [])
      setAudit(auditData.events || [])
    } catch {
      toast("加载用户失败", "error")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [])

  const suspiciousUsers = users.filter((user) => (user.risk_flags || []).length > 0)

  const submit = async () => {
    if (!form.username.trim() || !form.password) return
    try {
      await createUser({
        username: form.username.trim(),
        display_name: form.display_name.trim(),
        password: form.password,
        group_ids: [form.group_id],
        status: "active",
      })
      setForm({ username: "", display_name: "", password: "", group_id: "viewer" })
      toast("用户已创建", "success")
      void load()
    } catch {
      toast("创建用户失败", "error")
    }
  }

  const saveUser = async (user: AuthUser, patch: Record<string, unknown>) => {
    try {
      await updateUser(user.id, patch)
      toast("用户已更新", "success")
      void load()
    } catch {
      toast("更新失败", "error")
    }
  }

  const removeUser = async (user: AuthUser) => {
    if (!window.confirm(`确定删除用户 ${user.username} 吗？此操作会删除账号和用户组关系。`)) return
    try {
      await deleteUser(user.id)
      toast("用户已删除", "success")
      void load()
    } catch {
      toast("删除失败", "error")
    }
  }

  return (
    <div className="space-y-4">
      <Card title="创建用户">
        <div className="grid gap-2 sm:grid-cols-2 md:grid-cols-[10rem_10rem_10rem_10rem_auto]">
          <input className={INPUT} placeholder="用户名" value={form.username} onChange={(event) => setForm((prev) => ({ ...prev, username: event.target.value }))} />
          <input className={INPUT} placeholder="显示名" value={form.display_name} onChange={(event) => setForm((prev) => ({ ...prev, display_name: event.target.value }))} />
          <input className={INPUT} type="password" placeholder="初始密码" value={form.password} onChange={(event) => setForm((prev) => ({ ...prev, password: event.target.value }))} />
          <select className={INPUT} value={form.group_id} onChange={(event) => setForm((prev) => ({ ...prev, group_id: event.target.value }))}>
            {groups.map((group) => <option key={group.id} value={group.id}>{group.id}</option>)}
          </select>
          <Button className="sm:col-span-2 md:col-span-1" size="sm" onClick={submit}><UserPlus className="h-3 w-3" />创建</Button>
        </div>
      </Card>

      <Card
        title="用户与用户组"
        actions={
          <>
            <input
              className={`${INPUT} w-full sm:w-40`}
              value={ipFilter}
              onChange={(event) => setIpFilter(event.target.value)}
              onKeyDown={(event) => event.key === "Enter" && load()}
              placeholder="按 IP 筛选"
            />
            <Button variant="outline" size="sm" onClick={load} disabled={loading}>
              <RefreshCw className={`h-3 w-3 ${loading ? "animate-spin" : ""}`} />刷新
            </Button>
          </>
        }
      >
        {suspiciousUsers.length > 0 && (
          <div className="mb-3 rounded-xl border border-warning/30 bg-warning/10 p-3 text-xs text-default-700">
            <div className="mb-1 flex items-center gap-1.5 font-semibold text-warning-foreground">
              <AlertTriangle className="h-3.5 w-3.5" />
              可疑用户提醒
            </div>
            <div className="space-y-1">
              {suspiciousUsers.map((user) => (
                <div key={user.id}>
                  @{user.username}: {(user.risk_flags || []).join("、")}
                </div>
              ))}
            </div>
          </div>
        )}
        <div className="space-y-2">
          {users.map((user) => {
            const selected = new Set((user.groups || []).map((group) => group.id))
            return (
              <div key={user.id} className="rounded-xl border border-white/10 bg-content1/45 p-3">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-semibold">{user.display_name || user.username}</span>
                      {(user.risk_flags || []).length > 0 && (
                        <span className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[0.65rem] font-semibold ${user.risk_level === "high" ? "bg-destructive/15 text-destructive" : "bg-warning/15 text-warning-foreground"}`}>
                          <AlertTriangle className="h-3 w-3" />可疑
                        </span>
                      )}
                    </div>
                    <div className="text-xs text-default-500">
                      @{user.username} · {user.status} · 最近登录 {formatDate(user.last_login_at)}
                      {user.last_login_ip ? ` · ${user.last_login_ip}` : ""}
                      {user.locked_until ? ` · 锁定至 ${formatDate(user.locked_until)}` : ""}
                    </div>
                    {(user.risk_flags || []).length > 0 && (
                      <div className="mt-1 text-xs text-warning-foreground">{(user.risk_flags || []).join("、")}</div>
                    )}
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <select
                      className={INPUT}
                      value={user.status}
                      onChange={(event) => saveUser(user, { status: event.target.value })}
                    >
                      <option value="active">active</option>
                      <option value="disabled">disabled</option>
                    </select>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        const password = window.prompt(`重置 ${user.username} 的密码，至少 8 位`)
                        if (password) void saveUser(user, { password })
                      }}
                    >
                      重置密码
                    </Button>
                    <Button variant="destructive" size="sm" onClick={() => removeUser(user)}>
                      <Trash2 className="h-3 w-3" />删除
                    </Button>
                  </div>
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  {groups.map((group) => (
                    <label key={group.id} className="inline-flex cursor-pointer items-center gap-1.5 rounded-md border border-white/10 bg-default-100/40 px-2 py-1 text-xs text-default-700">
                      <input
                        type="checkbox"
                        checked={selected.has(group.id)}
                        onChange={(event) => {
                          const next = new Set(selected)
                          if (event.target.checked) next.add(group.id)
                          else next.delete(group.id)
                          void saveUser(user, { group_ids: Array.from(next) })
                        }}
                      />
                      {group.id}
                    </label>
                  ))}
                  <span className="inline-flex items-center gap-1 text-xs text-default-500">
                    <Save className="h-3 w-3" />勾选即保存
                  </span>
                </div>
              </div>
            )
          })}
        </div>
      </Card>

      <Card
        title="安全审计"
        actions={
          ipFilter.trim() ? (
            <span className="rounded-md bg-default-100/60 px-2 py-1 text-xs text-default-500">IP: {ipFilter.trim()}</span>
          ) : null
        }
      >
        {audit.length === 0 ? (
          <div className="flex min-h-36 items-center justify-center text-sm text-default-500">暂无审计记录</div>
        ) : (
          <div className="space-y-2">
            {audit.map((event) => (
              <div key={event.id} className="rounded-xl border border-white/10 bg-content1/45 p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex min-w-0 flex-wrap items-center gap-2">
                    <span className={`rounded-md px-2 py-0.5 text-[0.68rem] font-semibold ${event.success ? "bg-success/15 text-success" : "bg-destructive/15 text-destructive"}`}>
                      {event.success ? "成功" : "失败"}
                    </span>
                    <span className="text-sm font-medium">{event.event}</span>
                    <span className="text-xs text-default-500">@{event.username || event.user_id || "-"}</span>
                  </div>
                  <span className="text-xs text-default-500">{formatDate(event.created_at)}</span>
                </div>
                <div className="mt-1 text-xs text-default-500">
                  {event.ip || "-"}{event.detail ? ` · ${event.detail}` : ""}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  )
}
