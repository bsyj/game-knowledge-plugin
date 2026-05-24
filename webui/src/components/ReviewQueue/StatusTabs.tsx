import { RefreshCw } from "lucide-react"
import Button from "@/components/Button"
import { REVIEW_STATUSES, STATUS_DESCRIPTION, STATUS_LABEL } from "./constants"
import type { ReviewStats } from "./types"

interface Props {
  filter: string
  stats: ReviewStats | null
  loading: boolean
  legacyOnly: boolean
  onChangeFilter: (status: string) => void
  onToggleLegacy: () => void
  onRefresh: () => void
}

export default function StatusTabs({ filter, stats, loading, legacyOnly, onChangeFilter, onToggleLegacy, onRefresh }: Props) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="hide-scrollbar flex max-w-full gap-1 overflow-x-auto rounded-xl bg-default-100/60 p-1">
        {REVIEW_STATUSES.map((status) => {
          const count = stats?.[status] ?? 0
          const active = filter === status
          return (
            <button
              key={status}
              type="button"
              onClick={() => onChangeFilter(status)}
              title={STATUS_DESCRIPTION[status] || ""}
              className={`flex h-8 shrink-0 items-center gap-1.5 rounded-lg px-2.5 text-xs font-medium transition-colors ${
                active ? "bg-content1/65 text-default-900 shadow-sm" : "text-default-500 hover:text-default-900"
              }`}
            >
              <span>{STATUS_LABEL[status] || status}</span>
              <span
                className={`inline-flex h-4 min-w-[1.25rem] items-center justify-center rounded-full px-1 text-[0.65rem] font-semibold tabular-nums ${
                  active ? "bg-primary/15 text-primary" : "bg-default-100/70 text-default-500"
                }`}
              >
                {count}
              </span>
            </button>
          )
        })}
      </div>
      <button
        type="button"
        onClick={onToggleLegacy}
        title="只显示由旧 mc_chat_import paragraph 迁移生成的卡片（ai_review_status=legacy_import_migration）"
        className={`h-7 shrink-0 rounded-md px-2.5 text-xs font-medium transition-colors ${
          legacyOnly
            ? "border border-warning/40 bg-warning/15 text-warning-foreground"
            : "border border-white/10 bg-default-100/40 text-default-500 hover:text-default-900"
        }`}
      >
        {legacyOnly ? "✓ 仅旧导入" : "仅旧导入"}
      </button>
      <Button variant="outline" size="sm" onClick={onRefresh} disabled={loading} title="刷新列表与计数">
        <RefreshCw className={`h-3 w-3 ${loading ? "animate-spin" : ""}`} />
      </Button>
    </div>
  )
}
