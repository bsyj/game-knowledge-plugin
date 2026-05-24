import { Pencil } from "lucide-react"
import type { AuthUser } from "@/lib/api"
import { hasPermission } from "@/lib/api"
import { truncate } from "@/lib/utils"
import ActionButton from "./ActionButton"
import { STATUS_LABEL } from "./constants"
import { answerTypeLabel, similarColumnClass, similarStatusHint, statusBadgeClass, validStatusLabel } from "./utils"
import type { CardItem, SimilarCardItem } from "./types"

interface Props {
  card: CardItem
  user: AuthUser
  busyIds: Set<string>
  onApprove: (id: string) => void
  onReject: (id: string) => void
  onDelete: (id: string, options?: { skipConfirm?: boolean }) => void
  onEdit: (card: CardItem) => void
  onEditById: (id: string) => void
}

interface SlotCard extends Partial<SimilarCardItem> {
  id?: string | number
  workbenchRole: "current" | "candidate"
  score?: number
}

export default function DetailSimilar({ card, user, busyIds, onApprove, onReject, onDelete, onEdit, onEditById }: Props) {
  const canEdit = hasPermission(user, "knowledge.edit")
  const canApprove = hasPermission(user, "review.approve")
  const canReject = hasPermission(user, "review.reject")
  const canDelete = hasPermission(user, "knowledge.delete")
  const editorId = String(card.last_editor_id || "")
  const isOwnEdit = Boolean(editorId && editorId === user.id)

  const similar = Array.isArray(card.similar_cards) ? card.similar_cards : []
  const slots: SlotCard[] = [
    { ...card, score: undefined, workbenchRole: "current" },
    ...similar.map((item) => ({ ...item, workbenchRole: "candidate" as const })),
  ]

  return (
    <div className="grid gap-3">
      <div className="rounded-lg border border-warning/25 bg-warning/5 p-3 text-xs">
        <div className="text-[0.7rem] font-semibold text-warning-foreground">
          {card.review_status === "conflict" ? "版本冲突工作台" : "相似度判重工作台"}
        </div>
        <p className="mt-1 text-default-600">
          左侧为当前待审卡片，右侧为相似的候选/已有卡片。决定保留哪一张（或都保留 / 都删除）后，点击每张卡片下方的按钮各自处理。
        </p>
      </div>
      <div className="grid gap-3 xl:grid-cols-2">
        {slots.map((slot, index) => {
          const slotId = String(slot.id || "")
          const slotBusy = slotId ? busyIds.has(slotId) : false
          const slotStatus = String(slot.review_status || "")
          const slotIsCurrent = slot.workbenchRole === "current"
          const slotIsTerminal = slotStatus === "rejected" || slotStatus === "superseded"
          const slotCanApprove =
            !slotIsTerminal &&
            (slotStatus === "pending" ||
              slotStatus === "similar" ||
              slotStatus === "conflict" ||
              slotStatus === "ai_rejected")
          const slotCanReject = slotCanApprove || (!slotIsTerminal && slotStatus === "needs_answer")
          return (
            <div
              key={`${slot.workbenchRole}-${slot.id || index}`}
              className={`rounded-lg border border-white/10 p-3 text-xs transition-opacity ${similarColumnClass(slotStatus, slotIsCurrent)} ${slotIsTerminal ? "opacity-60 grayscale" : ""}`}
            >
              <div className="mb-2 flex flex-wrap items-center gap-1.5">
                <span
                  className={`rounded-md px-1.5 py-0.5 text-[0.62rem] font-semibold ${slotIsCurrent ? statusBadgeClass(card.review_status) : "border border-white/10 bg-default-100/60 text-default-500"}`}
                >
                  {slotIsCurrent ? "当前待审" : "候选/已有"} #{slot.id || "-"}
                </span>
                {slot.category && <span className="rounded-md bg-default-100/60 px-1.5 py-0.5 text-[0.62rem] font-semibold text-default-500">{slot.category}</span>}
                {slot.answer_type && <span className="rounded-md bg-default-100/60 px-1.5 py-0.5 text-[0.62rem] text-default-500">{answerTypeLabel(slot.answer_type)}</span>}
                {slot.valid_status && <span className="rounded-md bg-default-100/60 px-1.5 py-0.5 text-[0.62rem] text-default-500">{validStatusLabel(slot.valid_status)}</span>}
                {slot.rlcraft_version && (
                  <span className="rounded-md bg-warning/10 px-1.5 py-0.5 text-[0.62rem] font-semibold text-warning-foreground">版本 {slot.rlcraft_version}</span>
                )}
                {!slotIsCurrent && (
                  <span className="rounded-md bg-secondary/10 px-1.5 py-0.5 text-[0.62rem] font-semibold text-secondary">
                    相似度 {Math.round(Number(slot.score || 0) * 100)}%
                  </span>
                )}
                <span className="rounded-md bg-default-100/60 px-1.5 py-0.5 text-[0.62rem] text-default-500">
                  {similarStatusHint(slot.review_status) || STATUS_LABEL[slotStatus] || slotStatus}
                </span>
              </div>
              <div className="font-semibold text-default-900">{slot.title || slot.question || "未命名卡片"}</div>
              {slot.question && <div className="mt-1 text-default-500">Q: {truncate(slot.question, slotIsCurrent ? 240 : 160)}</div>}
              {slot.answer && <div className="mt-1 text-default-500">A: {truncate(slot.answer, slotIsCurrent ? 320 : 200)}</div>}
              <div className="mt-3 flex flex-wrap items-center gap-1.5">
                {slotIsTerminal ? (
                  <span className="inline-flex h-7 items-center gap-1 rounded-md border border-white/10 bg-default-100/60 px-2 text-[0.65rem] font-semibold text-default-500">
                    已处理 · {slotStatus === "rejected" ? "已拒绝" : "已被替代"}
                  </span>
                ) : (
                  <>
                    {canEdit && slotId && (
                      <button
                        type="button"
                        onClick={() => (slotIsCurrent ? onEdit(card) : onEditById(slotId))}
                        disabled={slotBusy}
                        className="inline-flex h-7 items-center gap-1 rounded-xl border border-white/10 bg-white/5 px-2.5 text-[0.7rem] font-semibold text-default-700 transition-colors hover:bg-white/10 hover:text-default-900 disabled:cursor-not-allowed disabled:opacity-50"
                        title="打开编辑器"
                      >
                        <Pencil className="h-3 w-3" />
                        编辑
                      </button>
                    )}
                    {slotId && slotCanApprove && (
                      <ActionButton
                        status={slotStatus || card.review_status}
                        action="approve"
                        onClick={() => onApprove(slotId)}
                        busy={slotBusy}
                        disabledByPermission={!canApprove}
                        isOwnEdit={slotIsCurrent && isOwnEdit}
                      />
                    )}
                    {slotId && slotCanReject && (
                      <ActionButton
                        status={slotStatus || card.review_status}
                        action="reject"
                        onClick={() => onReject(slotId)}
                        busy={slotBusy}
                        disabledByPermission={!canReject}
                        isOwnEdit={slotIsCurrent && isOwnEdit}
                      />
                    )}
                    {slotId && (
                      <ActionButton
                        status={slotStatus || card.review_status}
                        action="delete"
                        onClick={() => onDelete(slotId, { skipConfirm: true })}
                        busy={slotBusy}
                        disabledByPermission={!canDelete}
                      />
                    )}
                  </>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
