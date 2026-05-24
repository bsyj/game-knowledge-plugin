import { ChevronLeft, Inbox } from "lucide-react"
import type { AuthUser } from "@/lib/api"
import DetailNormal from "./DetailNormal"
import DetailSimilar from "./DetailSimilar"
import { isQuestionCard } from "./utils"
import type { CardItem } from "./types"

interface Props {
  card: CardItem | null
  user: AuthUser
  busyIds: Set<string>
  mobileMode: boolean
  onBack: () => void
  onApprove: (id: string) => void
  onReject: (id: string) => void
  onQuestion: (id: string) => void
  onDelete: (id: string, options?: { skipConfirm?: boolean }) => void
  onEdit: (card: CardItem) => void
  onEditById: (id: string) => void
  onFilterByGroup: (groupId: string, groupName: string) => void
}

export default function DetailPane({
  card,
  user,
  busyIds,
  mobileMode,
  onBack,
  onApprove,
  onReject,
  onQuestion,
  onDelete,
  onEdit,
  onEditById,
  onFilterByGroup,
}: Props) {
  if (!card) {
    return (
      <div className="flex h-full min-h-[20rem] flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-white/10 bg-content1/20 p-6 text-center text-sm text-default-500">
        <Inbox className="h-6 w-6 text-default-400" />
        <p>左侧选择一张卡片查看详情</p>
        <p className="text-[0.7rem] text-default-400">键盘 ↓ / j 可快速浏览</p>
      </div>
    )
  }

  const status = String(card.review_status || "")
  const busy = busyIds.has(String(card.id))
  const isSimilarMode = status === "similar" || status === "conflict"
  const variant = isQuestionCard(card) || status === "needs_answer" ? "question" : "normal"

  return (
    <div className="flex h-full flex-col">
      {mobileMode && (
        <button
          type="button"
          onClick={onBack}
          className="mb-2 inline-flex w-fit items-center gap-1 rounded-md border border-white/10 bg-content1/40 px-2 py-1 text-xs text-default-600 hover:text-default-900"
        >
          <ChevronLeft className="h-3 w-3" />
          返回列表
        </button>
      )}
      <div className="min-h-0 flex-1 overflow-y-auto pr-1">
        {isSimilarMode ? (
          <DetailSimilar
            card={card}
            user={user}
            busyIds={busyIds}
            onApprove={onApprove}
            onReject={onReject}
            onDelete={onDelete}
            onEdit={onEdit}
            onEditById={onEditById}
          />
        ) : (
          <DetailNormal
            card={card}
            user={user}
            busy={busy}
            variant={variant}
            onApprove={onApprove}
            onReject={onReject}
            onQuestion={onQuestion}
            onDelete={onDelete}
            onEdit={onEdit}
            onFilterByGroup={onFilterByGroup}
          />
        )}
      </div>
    </div>
  )
}
