import { Loader2 } from "lucide-react"
import { truncate } from "@/lib/utils"
import { STATUS_LABEL } from "./constants"
import { answerTypeLabel, cardBorderClass, relativeTime, statusBadgeClass } from "./utils"
import type { CardItem } from "./types"

interface Props {
  cards: CardItem[]
  loading: boolean
  selectedId: string | null
  bulkSelection: Set<string>
  bulkMode: boolean
  currentUserId: string
  hasMore: boolean
  loadingMore: boolean
  filterLabel: string
  onSelect: (card: CardItem) => void
  onToggleBulk: (id: string) => void
  onToggleAll: () => void
  onLoadMore: () => void
}

export default function ListPane({
  cards,
  loading,
  selectedId,
  bulkSelection,
  bulkMode,
  currentUserId,
  hasMore,
  loadingMore,
  filterLabel,
  onSelect,
  onToggleBulk,
  onToggleAll,
  onLoadMore,
}: Props) {
  const allSelected = cards.length > 0 && cards.every((card) => bulkSelection.has(String(card.id)))
  const someSelected = bulkSelection.size > 0 && !allSelected
  return (
    <div className="flex h-full min-h-0 flex-col rounded-xl border border-black/10 bg-content1/20 dark:border-white/10">
      <div className="flex items-center justify-between gap-2 border-b border-white/5 px-3 py-2 text-xs text-default-500">
        <label className="inline-flex cursor-pointer select-none items-center gap-2">
          <input
            type="checkbox"
            checked={allSelected}
            ref={(el) => {
              if (el) el.indeterminate = someSelected
            }}
            onChange={onToggleAll}
            className="h-3.5 w-3.5 cursor-pointer rounded border-default-300 text-primary focus:ring-primary/40"
            title="全选/反选当前页"
          />
          <span>
            {bulkMode ? `已选 ${bulkSelection.size} / ${cards.length}` : `共 ${cards.length} 张`}
          </span>
        </label>
        {loading && (
          <span className="inline-flex items-center gap-1 text-default-500">
            <Loader2 className="h-3 w-3 animate-spin" />
            加载中
          </span>
        )}
      </div>
      <div className="hide-scrollbar min-h-0 flex-1 overflow-y-auto">
        {cards.length === 0 && !loading ? (
          <div className="flex h-full min-h-[16rem] items-center justify-center px-4 text-sm text-default-500">
            暂无 {filterLabel} 的卡片
          </div>
        ) : (
          <ul className="divide-y divide-white/5">
            {cards.map((card) => {
              const id = String(card.id)
              const status = String(card.review_status || "")
              const checked = bulkSelection.has(id)
              const active = selectedId === id
              const editorName = String(card.last_editor_name || card.last_editor_id || "系统/AI")
              const isOwn = Boolean(card.last_editor_id && card.last_editor_id === currentUserId)
              return (
                <li key={id}>
                  <div
                    role="button"
                    tabIndex={0}
                    onClick={() => onSelect(card)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault()
                        onSelect(card)
                      }
                    }}
                    className={`group relative grid cursor-pointer grid-cols-[auto_1fr_auto] items-start gap-2 border-l-2 px-3 py-2.5 transition-colors ${
                      active
                        ? "border-l-primary bg-primary/10"
                        : `border-l-transparent hover:bg-default-100/30 ${cardBorderClass(status)}`
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onClick={(event) => event.stopPropagation()}
                      onChange={() => onToggleBulk(id)}
                      className="mt-1 h-3.5 w-3.5 cursor-pointer rounded border-default-300 text-primary focus:ring-primary/40"
                      title="勾选用于批量操作"
                    />
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-1 text-[0.65rem] font-semibold">
                        <span className={`rounded px-1.5 py-0.5 ${statusBadgeClass(status)}`}>{STATUS_LABEL[status] || status}</span>
                        <span className="rounded bg-primary/15 px-1.5 py-0.5 text-primary">#{card.id}</span>
                        {card.category && (
                          <span className="rounded border border-white/10 bg-default-100/60 px-1.5 py-0.5 text-default-500">{card.category}</span>
                        )}
                        {card.answer_type && (
                          <span className="rounded border border-white/10 bg-default-100/60 px-1.5 py-0.5 text-default-500">{answerTypeLabel(card.answer_type)}</span>
                        )}
                        {card.rlcraft_version && (
                          <span className="rounded border border-warning/25 bg-warning/10 px-1.5 py-0.5 text-warning-foreground">v{card.rlcraft_version}</span>
                        )}
                      </div>
                      <h4 className="mt-1 truncate text-sm font-semibold text-default-900">
                        {card.title || truncate(card.question || "未命名", 80) || `卡片 #${card.id}`}
                      </h4>
                      <div className="mt-0.5 flex flex-wrap items-center gap-1 text-[0.7rem] text-default-500">
                        <span>编辑 {Number(card.edit_count || 0)} 次</span>
                        <span>·</span>
                        <span className="truncate">
                          {editorName}{isOwn ? " (你)" : ""}
                        </span>
                        <span>·</span>
                        <span>{relativeTime(card.updated_at || card.created_at)}</span>
                        {card.source_group_name && (
                          <>
                            <span>·</span>
                            <span className="truncate text-default-400" title={card.source_group_name}>来自 {card.source_group_name}</span>
                          </>
                        )}
                      </div>
                    </div>
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </div>
      {hasMore && (
        <button
          type="button"
          onClick={onLoadMore}
          disabled={loadingMore}
          className="shrink-0 border-t border-white/5 px-3 py-2 text-center text-xs text-default-500 hover:bg-default-100/30 disabled:opacity-50"
        >
          {loadingMore ? "加载中…" : "加载更多"}
        </button>
      )}
    </div>
  )
}
