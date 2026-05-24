import { cn } from "@/lib/utils"
import type { LucideIcon } from "lucide-react"

export interface Tab {
  key: string
  label: string
  icon: LucideIcon
}

interface Props {
  tabs: Tab[]
  active: string
  onChange: (key: string) => void
}

export default function TabNav({ tabs, active, onChange }: Props) {
  return (
    <nav className="hide-scrollbar inline-flex max-w-full items-center gap-0 overflow-x-auto rounded-xl bg-default-100/60 p-0.5">
      {tabs.map((tab) => (
        <button
          key={tab.key}
          onClick={() => onChange(tab.key)}
          className={cn(
            "inline-flex h-7 shrink-0 items-center justify-center gap-1.5 rounded-md px-2.5 text-xs font-medium transition-colors",
            active === tab.key
              ? "bg-content1/45 text-default-900 shadow-sm"
              : "text-default-500 hover:text-default-900",
          )}
        >
          <tab.icon className="h-3.5 w-3.5" />
          <span className="hidden sm:inline">{tab.label}</span>
        </button>
      ))}
    </nav>
  )
}
