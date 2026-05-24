import { useEffect, useState } from "react"
import { KeyRound, Loader2, Moon, Send, ShieldCheck, Sun, UserPlus } from "lucide-react"
import {
  bootstrapAdmin,
  fetchBootstrapStatus,
  fetchMe,
  getAuthToken,
  login,
  register,
  requestRegistrationCaptcha,
  setAuthToken,
  type AuthSettings,
  type AuthUser,
} from "@/lib/api"
import Button from "@/components/Button"

const INPUT = "napcat-input h-10 rounded-xl px-3 text-sm transition-colors"

interface Props {
  theme: "dark" | "light"
  onThemeToggle: () => void
  onReady: (user: AuthUser) => void
}

export default function AuthGate({ theme, onThemeToggle, onReady }: Props) {
  const [loading, setLoading] = useState(true)
  const [bootstrap, setBootstrap] = useState(false)
  const [mode, setMode] = useState<"login" | "register">("login")
  const [settings, setSettings] = useState<AuthSettings | null>(null)
  const [busy, setBusy] = useState(false)
  const [captchaBusy, setCaptchaBusy] = useState(false)
  const [captchaCooldown, setCaptchaCooldown] = useState(0)
  const [error, setError] = useState("")
  const [form, setForm] = useState({ username: "admin", display_name: "", password: "", captcha: "" })
  const subtitle = bootstrap ? "创建第一个 admin 账号后启用权限系统" : mode === "login" ? "输入账号和密码进入" : ""

  useEffect(() => {
    let alive = true
    async function init() {
      setLoading(true)
      setError("")
      try {
        const status = await fetchBootstrapStatus()
        if (!alive) return
        setBootstrap(!status.has_users)
        setSettings(status.settings || null)
        if (status.has_users && getAuthToken()) {
          const me = await fetchMe()
          if (alive) onReady(me.user)
        }
      } catch {
        if (alive) setError("认证服务暂时不可用")
      } finally {
        if (alive) setLoading(false)
      }
    }
    void init()
    return () => { alive = false }
  }, [onReady])

  useEffect(() => {
    if (captchaCooldown <= 0) return
    const timer = window.setInterval(() => {
      setCaptchaCooldown((value) => Math.max(0, value - 1))
    }, 1000)
    return () => window.clearInterval(timer)
  }, [captchaCooldown])

  const errorMessage = (error: unknown, fallback: string) => {
    return typeof error === "object" && error && "response" in error
      ? String((error as { response?: { data?: { error?: string } } }).response?.data?.error || fallback)
      : fallback
  }

  const requestCaptcha = async () => {
    if (!form.username.trim() || captchaCooldown > 0) return
    setCaptchaBusy(true)
    setError("")
    try {
      const result = await requestRegistrationCaptcha({ username: form.username.trim() })
      setCaptchaCooldown(Number(result.cooldown_seconds || settings?.registration_captcha_cooldown_seconds || 3600))
    } catch (error) {
      const remaining = typeof error === "object" && error && "response" in error
        ? Number((error as { response?: { data?: { cooldown_remaining?: number } } }).response?.data?.cooldown_remaining || 0)
        : 0
      if (remaining > 0) setCaptchaCooldown(remaining)
      setError(errorMessage(error, "验证码发送失败，请确认 QQ 号在注册群内"))
    } finally {
      setCaptchaBusy(false)
    }
  }

  const submit = async () => {
    if (!form.username.trim() || !form.password) return
    if (!bootstrap && mode === "register" && !form.captcha.trim()) {
      setError("请输入验证码")
      return
    }
    setBusy(true)
    setError("")
    try {
      const result = bootstrap
        ? await bootstrapAdmin(form)
        : mode === "register"
          ? await register(form)
          : await login({ username: form.username, password: form.password })
      setAuthToken(result.token)
      onReady(result.user)
    } catch (error) {
      setError(errorMessage(error, bootstrap ? "初始化失败，请检查用户名和密码" : mode === "register" ? "注册失败，请检查信息" : "登录失败，请检查用户名和密码"))
    } finally {
      setBusy(false)
    }
  }

  if (loading) {
    return (
      <div className="grid min-h-[100dvh] place-items-center text-default-900">
        <div className="inline-flex items-center gap-2 text-sm text-default-500">
          <Loader2 className="h-4 w-4 animate-spin" />
          正在连接 GameKnowledge
        </div>
      </div>
    )
  }

  return (
    <div className="grid min-h-[100dvh] place-items-center p-4 text-default-900">
      <div className="napcat-glass relative w-full max-w-[27rem] rounded-2xl p-4 sm:p-5">
        <button
          type="button"
          className="absolute right-4 top-4 inline-flex h-8 w-8 items-center justify-center rounded-xl border border-[var(--gk-input-border)] bg-[var(--gk-input-bg)] text-default-500 transition-colors hover:bg-default-100/70 hover:text-default-900"
          onClick={onThemeToggle}
          aria-label={theme === "dark" ? "切换到亮色主题" : "切换到暗色主题"}
          title={theme === "dark" ? "切换到亮色主题" : "切换到暗色主题"}
        >
          {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
        </button>
        <div className="mb-5 flex items-center gap-3">
          <div className="grid h-11 w-11 place-items-center rounded-2xl bg-primary text-primary-foreground">
            {bootstrap ? <ShieldCheck className="h-5 w-5" /> : mode === "register" ? <UserPlus className="h-5 w-5" /> : <KeyRound className="h-5 w-5" />}
          </div>
          <div className="min-w-0 pr-10">
            <h1 className="text-lg font-semibold tracking-tight">{bootstrap ? "初始化管理员" : mode === "register" ? "注册 GameKnowledge" : "登录 GameKnowledge"}</h1>
            {subtitle && <p className="text-xs text-default-500">{subtitle}</p>}
          </div>
        </div>

        {!bootstrap && settings?.allow_registration && (
          <div className="mb-4 grid grid-cols-2 rounded-xl bg-default-100/55 p-1">
            <button
              type="button"
              className={`h-8 rounded-lg text-xs font-semibold transition-colors ${mode === "login" ? "bg-content1 text-default-900 shadow-sm" : "text-default-500 hover:text-default-900"}`}
              onClick={() => setMode("login")}
            >
              登录
            </button>
            <button
              type="button"
              className={`h-8 rounded-lg text-xs font-semibold transition-colors ${mode === "register" ? "bg-content1 text-default-900 shadow-sm" : "text-default-500 hover:text-default-900"}`}
              onClick={() => setMode("register")}
            >
              注册
            </button>
          </div>
        )}

        <div className="grid gap-3">
          <label className="grid gap-1 text-xs text-default-500">
            {!bootstrap && mode === "register" ? "QQ号" : "用户名"}
            <input className={INPUT} value={form.username} onChange={(event) => setForm((prev) => ({ ...prev, username: event.target.value }))} placeholder={!bootstrap && mode === "register" ? "请输入注册群内 QQ 号" : "3-32 位字母、数字、_ 或 -"} />
          </label>
          {(bootstrap || mode === "register") && (
            <label className="grid gap-1 text-xs text-default-500">
              昵称
              <input className={INPUT} value={form.display_name} onChange={(event) => setForm((prev) => ({ ...prev, display_name: event.target.value }))} placeholder="最多 40 个字符" />
            </label>
          )}
          <label className="grid gap-1 text-xs text-default-500">
            密码
            <input
              className={INPUT}
              type="password"
              value={form.password}
              onChange={(event) => setForm((prev) => ({ ...prev, password: event.target.value }))}
              onKeyDown={(event) => event.key === "Enter" && submit()}
              placeholder="8-128 位"
            />
          </label>
          {!bootstrap && mode === "register" && (
            <label className="grid gap-1 text-xs text-default-500">
              验证码
              <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_7rem]">
                <input className={INPUT} value={form.captcha} onChange={(event) => setForm((prev) => ({ ...prev, captcha: event.target.value }))} placeholder="6 位验证码" />
                <button
                  type="button"
                  className="inline-flex h-10 items-center justify-center gap-1 rounded-xl border border-[var(--gk-input-border)] bg-[var(--gk-input-bg)] px-2 text-xs font-semibold text-default-600 transition-colors hover:border-primary hover:text-primary disabled:cursor-not-allowed disabled:opacity-60"
                  disabled={captchaBusy || captchaCooldown > 0 || !form.username.trim()}
                  onClick={requestCaptcha}
                >
                  {captchaBusy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
                  {captchaCooldown > 0 ? `${Math.ceil(captchaCooldown / 60)}分钟` : "获取验证码"}
                </button>
              </div>
            </label>
          )}
          {error && <p className="rounded-xl border border-destructive/30 bg-destructive/15 px-3 py-2 text-xs text-destructive">{error}</p>}
          <Button onClick={submit} disabled={busy || !form.username.trim() || !form.password || (!bootstrap && mode === "register" && !form.captcha.trim())}>
            {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            {bootstrap ? "创建管理员" : mode === "register" ? "注册并进入" : "登录"}
          </Button>
        </div>
      </div>
    </div>
  )
}
