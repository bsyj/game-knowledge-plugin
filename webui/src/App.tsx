import { useEffect, useMemo, useState } from "react"
import { AnimatePresence, motion } from "framer-motion"
import {
  Database,
  Gauge,
  LibraryBig,
  LogOut,
  Megaphone,
  MessageSquareQuote,
  Moon,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
  Send,
  Sparkles,
  UserCog,
  UserRound,
  ShieldCheck,
  Sun,
} from "lucide-react"
import { Chip } from "@heroui/react"
import { ToastProvider } from "@/components/Toast"
import AnnouncementBanner from "@/components/AnnouncementBanner"
import AnnouncementsPanel from "@/components/AnnouncementsPanel"
import AuthGate from "@/components/AuthGate"
import BoardPanel from "@/components/BoardPanel"
import Dashboard from "@/components/Dashboard"
import ReviewQueue from "@/components/ReviewQueue"
import SearchPanel from "@/components/SearchPanel"
import IngestPanel from "@/components/ImportPanel"
import SourcesPanel from "@/components/SourcesPanel"
import ProfilePanel from "@/components/ProfilePanel"
import QualityTuningPanel from "@/components/QualityTuningPanel"
import UsersPanel from "@/components/UsersPanel"
import { hasPermission, setAuthToken, type AuthUser } from "@/lib/api"
import { cn } from "@/lib/utils"

type ThemeMode = "dark" | "light"

interface NavItem {
  key: string
  label: string
  desc: string
  icon: typeof Gauge
  permission: string
}

const NAV_ITEMS: NavItem[] = [
  { key: "dashboard", label: "仪表盘", desc: "运行概览", icon: Gauge, permission: "dashboard.view" },
  { key: "announcements", label: "公告", desc: "管理员通告", icon: Megaphone, permission: "announcement.view" },
  { key: "board", label: "留言板", desc: "群友问答 · 入库审核", icon: MessageSquareQuote, permission: "board.view" },
  { key: "search", label: "知识检索", desc: "查询与修订", icon: Search, permission: "knowledge.search" },
  { key: "ingest", label: "写入导入", desc: "手动补充", icon: Send, permission: "knowledge.create" },
  { key: "review", label: "审核队列", desc: "AI 与人工审核", icon: ShieldCheck, permission: "review.view" },
  { key: "qualityTuning", label: "随机调优", desc: "抽检入库卡片", icon: Sparkles, permission: "*" },
  { key: "sources", label: "来源管理", desc: "群与数据源", icon: Database, permission: "sources.manage" },
  { key: "profile", label: "个人中心", desc: "编辑历史", icon: UserRound, permission: "history.view_own" },
  { key: "users", label: "用户管理", desc: "用户组权限", icon: UserCog, permission: "users.manage" },
]

const TITLE: Record<string, string> = {
  dashboard: "仪表盘",
  announcements: "公告",
  board: "留言板",
  search: "知识检索",
  ingest: "写入导入",
  review: "审核队列",
  qualityTuning: "随机调优",
  sources: "来源管理",
  profile: "个人中心",
  users: "用户管理",
}

const pageMotion = {
  initial: { opacity: 0, y: 14, filter: "blur(10px)", scale: 0.992 },
  animate: { opacity: 1, y: 0, filter: "blur(0px)" },
  exit: { opacity: 0, y: -8, filter: "blur(6px)", scale: 0.996 },
}

function applyTheme(theme: ThemeMode) {
  document.documentElement.dataset.theme = theme
  document.documentElement.classList.toggle("dark", theme === "dark")
  document.documentElement.classList.toggle("light", theme === "light")
  localStorage.setItem("gk-webui-theme", theme)
}

function ThemeSwitch({ theme, onToggle }: { theme: ThemeMode; onToggle: () => void }) {
  const isDark = theme === "dark"
  return (
    <motion.button
      type="button"
      onClick={onToggle}
      className={cn(
        "theme-switch group relative inline-grid h-8 w-[4.5rem] grid-cols-2 items-center rounded-full border border-[var(--gk-input-border)] bg-[var(--gk-input-bg)] p-1 shadow-sm transition-colors",
      )}
      aria-label={isDark ? "切换到亮色主题" : "切换到暗色主题"}
      whileTap={{ scale: 0.96 }}
    >
      <span className={cn("relative z-10 flex h-6 w-6 items-center justify-center rounded-full text-[0.65rem] transition-colors", isDark ? "text-default-500" : "text-amber-500")}>
        <Sun className="h-3.5 w-3.5" />
      </span>
      <span className={cn("relative z-10 flex h-6 w-6 items-center justify-center rounded-full text-[0.65rem] transition-colors", isDark ? "text-indigo-300" : "text-default-400")}>
        <Moon className="h-3.5 w-3.5" />
      </span>
      <motion.span
        className={cn(
          "absolute left-1 top-1 h-6 w-6 rounded-full shadow-lg",
          isDark ? "bg-default-200 shadow-black/45 ring-1 ring-white/15" : "bg-white shadow-indigo-200/80 ring-1 ring-black/5",
        )}
        animate={{ x: isDark ? 40 : 0 }}
        transition={{ type: "spring", stiffness: 520, damping: 34 }}
      />
    </motion.button>
  )
}

function BackgroundAura() {
  return (
    <div className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
      <motion.div
        className="absolute left-[-10%] top-[-10%] h-[500px] w-[500px] rounded-full bg-primary/18 blur-[100px]"
        animate={{ x: [0, 18, -8, 0], y: [0, 12, -10, 0], scale: [1, 1.05, 0.98, 1] }}
        transition={{ duration: 18, repeat: Infinity, ease: "easeInOut" }}
      />
      <motion.div
        className="absolute right-[-10%] top-[18%] h-[420px] w-[420px] rounded-full bg-secondary/16 blur-[92px]"
        animate={{ x: [0, -14, 12, 0], y: [0, -8, 16, 0], scale: [1, 0.96, 1.04, 1] }}
        transition={{ duration: 20, repeat: Infinity, ease: "easeInOut" }}
      />
      <motion.div
        className="absolute bottom-[-16%] left-[18%] h-[620px] w-[620px] rounded-full bg-primary/10 blur-[112px]"
        animate={{ x: [0, 24, 6, 0], y: [0, -16, 10, 0] }}
        transition={{ duration: 24, repeat: Infinity, ease: "easeInOut" }}
      />
    </div>
  )
}

function SidebarItem({ item, active, collapsed, onClick }: { item: NavItem; active: boolean; collapsed: boolean; onClick: () => void }) {
  const Icon = item.icon
  return (
    <motion.button
      type="button"
      onClick={onClick}
      whileHover={collapsed ? { scale: 1.04 } : { x: 2 }}
      whileTap={{ scale: 0.985 }}
      title={collapsed ? `${item.label} · ${item.desc}` : undefined}
      className={cn(
        "group relative flex w-full items-center overflow-hidden rounded-2xl text-left transition-colors",
        collapsed ? "justify-center px-1.5 py-2" : "gap-3 px-3 py-2.5",
        active ? "text-primary-foreground" : "text-default-500 hover:bg-default-100/60 hover:text-default-900",
      )}
    >
      {active && (
        <motion.span
          layoutId="napcat-sidebar-active"
          className="absolute inset-0 rounded-2xl bg-primary/20 shadow-[0_10px_28px_rgb(129_140_248_/_0.24)] ring-1 ring-primary/35"
          transition={{ type: "spring", stiffness: 420, damping: 34 }}
        />
      )}
      <span
        className={cn(
          "relative flex h-9 w-9 items-center justify-center rounded-xl transition-colors",
          active ? "bg-primary text-primary-foreground" : "bg-default-100/60 text-default-500 group-hover:bg-default-200/70",
        )}
      >
        <Icon className="h-4 w-4" />
      </span>
      {!collapsed && (
        <span className="relative min-w-0">
          <span className={cn("block text-sm font-semibold leading-5", active && "shiny-text")}>{item.label}</span>
          <span className="block truncate text-xs text-default-500">{item.desc}</span>
        </span>
      )}
    </motion.button>
  )
}

export default function App() {
  const [activeTab, setActiveTab] = useState("dashboard")
  const [user, setUser] = useState<AuthUser | null>(null)
  const [theme, setTheme] = useState<ThemeMode>(() => {
    const saved = localStorage.getItem("gk-webui-theme")
    return saved === "light" ? "light" : "dark"
  })
  const [sidebarCollapsed, setSidebarCollapsed] = useState<boolean>(() => {
    return localStorage.getItem("gk-webui-sidebar-collapsed") === "1"
  })

  useEffect(() => { applyTheme(theme) }, [theme])
  useEffect(() => {
    localStorage.setItem("gk-webui-sidebar-collapsed", sidebarCollapsed ? "1" : "0")
  }, [sidebarCollapsed])

  const visibleNav = useMemo(() => NAV_ITEMS.filter((item) => hasPermission(user, item.permission)), [user])

  useEffect(() => {
    if (!user) return
    const active = NAV_ITEMS.find((item) => item.key === activeTab)
    if (!active || !hasPermission(user, active.permission)) {
      setActiveTab(visibleNav[0]?.key || "dashboard")
    }
  }, [activeTab, user, visibleNav])

  const page = useMemo(() => {
    if (!user) return null
    if (activeTab === "review") return <ReviewQueue user={user} />
    if (activeTab === "qualityTuning") return <QualityTuningPanel />
    if (activeTab === "search") return <SearchPanel user={user} />
    if (activeTab === "ingest") return <IngestPanel />
    if (activeTab === "sources") return <SourcesPanel />
    if (activeTab === "profile") return <ProfilePanel user={user} onUserChange={setUser} />
    if (activeTab === "users") return <UsersPanel />
    if (activeTab === "announcements") return <AnnouncementsPanel user={user} />
    if (activeTab === "board") return <BoardPanel user={user} />
    return <Dashboard onNavigate={setActiveTab} user={user} />
  }, [activeTab, user])

  if (!user) {
    return (
      <ToastProvider>
        <AuthGate
          theme={theme}
          onThemeToggle={() => setTheme(theme === "dark" ? "light" : "dark")}
          onReady={setUser}
        />
      </ToastProvider>
    )
  }

  return (
    <ToastProvider>
      <BackgroundAura />
      <div className="min-h-[100dvh] overflow-hidden text-default-900 sm:p-3 md:p-5">
        <div className="mx-auto flex h-[100dvh] max-w-[1536px] overflow-hidden border bg-[var(--gk-shell-bg)] shadow-[var(--gk-shell-shadow)] backdrop-blur-xl sm:h-[calc(100dvh-1.5rem)] sm:rounded-[28px] md:h-[calc(100dvh-2.5rem)]" style={{ borderColor: "var(--gk-shell-border)" }}>
          <aside
            className={cn(
              "hidden shrink-0 border-r bg-[var(--gk-sidebar-bg)] transition-[width,padding] duration-300 ease-in-out md:flex md:flex-col",
              sidebarCollapsed ? "w-[68px] p-2" : "w-72 p-4",
            )}
            style={{ borderColor: "var(--gk-shell-border)" }}
          >
            <div className={cn("mb-7 flex items-center px-1", sidebarCollapsed ? "justify-center" : "justify-between gap-2")}>
              {!sidebarCollapsed && (
                <div className="flex min-w-0 items-center gap-3">
                  <motion.div
                    className="flex h-11 w-11 items-center justify-center rounded-2xl bg-primary/15 ring-1 ring-primary/30"
                    whileHover={{ rotate: -4, scale: 1.04 }}
                    transition={{ type: "spring", stiffness: 360, damping: 22 }}
                  >
                    <LibraryBig className="h-5 w-5 text-primary" />
                  </motion.div>
                  <div className="min-w-0">
                    <div className="napcat-cute text-xl font-bold tracking-tight">GameKnowledge</div>
                    <div className="text-xs text-default-500">MaiBot 游戏知识库</div>
                  </div>
                </div>
              )}
              <button
                type="button"
                onClick={() => setSidebarCollapsed((prev) => !prev)}
                title={sidebarCollapsed ? "展开侧边栏" : "收起侧边栏"}
                aria-label={sidebarCollapsed ? "展开侧边栏" : "收起侧边栏"}
                className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border border-[var(--gk-input-border)] bg-[var(--gk-input-bg)] text-default-500 transition-colors hover:bg-default-100/70 hover:text-default-900"
              >
                {sidebarCollapsed ? <PanelLeftOpen className="h-4 w-4" /> : <PanelLeftClose className="h-4 w-4" />}
              </button>
            </div>

            <nav className="hide-scrollbar space-y-2 overflow-y-auto">
              {visibleNav.map((item) => (
                <SidebarItem
                  key={item.key}
                  item={item}
                  active={activeTab === item.key}
                  collapsed={sidebarCollapsed}
                  onClick={() => setActiveTab(item.key)}
                />
              ))}
            </nav>
          </aside>

          <main className="flex min-w-0 flex-1 flex-col">
            <header className="sticky top-0 z-20 border-b bg-[var(--gk-header-bg)] px-3 py-3 backdrop-blur-xl sm:px-4 md:px-6" style={{ borderColor: "var(--gk-shell-border)" }}>
              <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                <div className="flex min-w-0 items-center gap-3">
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-2xl bg-primary/15 md:hidden">
                    <LibraryBig className="h-4 w-4 text-primary" />
                  </div>
                  <div className="hidden h-10 w-10 items-center justify-center rounded-2xl bg-default-100/70 md:flex">
                    <LibraryBig className="h-5 w-5 text-primary" />
                  </div>
                  <div className="min-w-0">
                    <h1 className="truncate text-lg font-bold tracking-tight sm:text-xl">{TITLE[activeTab] || "GameKnowledge"}</h1>
                    <p className="truncate text-xs text-default-500">专注游戏知识提取、审核、检索和管理</p>
                  </div>
                </div>
                <div className="flex min-w-0 flex-wrap items-center gap-2">
                  <Chip size="sm" variant="soft" color="accent" className="shiny-text">WebUI</Chip>
                  <Chip size="sm" variant="soft" color="default" className="max-w-[8.5rem] truncate sm:max-w-[14rem]">{user.display_name || user.username}</Chip>
                  <button
                    type="button"
                    className="inline-flex h-7 items-center gap-1 rounded-full border border-[var(--gk-input-border)] px-2 text-xs text-default-500 transition-colors hover:bg-default-100/60 hover:text-default-900"
                    onClick={() => {
                      setAuthToken("")
                      setUser(null)
                    }}
                  >
                    <LogOut className="h-3 w-3" />退出
                  </button>
                  <ThemeSwitch theme={theme} onToggle={() => setTheme(theme === "dark" ? "light" : "dark")} />
                </div>
              </div>

              <div className="hide-scrollbar -mx-1 mt-3 flex snap-x gap-2 overflow-x-auto px-1 pb-0.5 md:hidden">
                {visibleNav.map((item) => {
                  const Icon = item.icon
                  return (
                    <button
                      key={item.key}
                      type="button"
                      onClick={() => setActiveTab(item.key)}
                      className={cn(
                        "inline-flex shrink-0 snap-start items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium transition-colors",
                        activeTab === item.key ? "bg-primary text-primary-foreground" : "bg-default-100/60 text-default-500",
                      )}
                    >
                      <Icon className="h-3.5 w-3.5" />
                      {item.label}
                    </button>
                  )
                })}
              </div>
            </header>

            <div className="min-h-0 flex-1 overscroll-contain overflow-y-auto p-3 sm:p-4 md:p-6">
              <AnnouncementBanner onJump={() => setActiveTab("announcements")} />
              <AnimatePresence mode="wait">
                <motion.div
                  className="h-full min-h-0"
                  key={activeTab}
                  initial={pageMotion.initial}
                  animate={pageMotion.animate}
                  exit={pageMotion.exit}
                  transition={{ duration: 0.26, ease: [0.22, 1, 0.36, 1] }}
                >
                  {page}
                </motion.div>
              </AnimatePresence>
            </div>
          </main>
        </div>
      </div>
    </ToastProvider>
  )
}
