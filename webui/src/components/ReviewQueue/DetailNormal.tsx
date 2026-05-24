import { Loader2, Pencil } from "lucide-react"
import type { AuthUser } from "@/lib/api"
import { hasPermission } from "@/lib/api"
import { formatDate, truncate } from "@/lib/utils"
import ActionButton from "./ActionButton"
import AIVerdictCard from "./AIVerdictCard"
import SourceBlock from "./SourceBlock"
import RevisionDiff from "./RevisionDiff"
import { PROCESSING_HINT, STATUS_LABEL } from "./constants"
import { answerTypeLabel, cardBorderClass, questionOrigin, questionReviewParts, relativeTime, statusBadgeClass, validStatusLabel } from "./utils"
import type { CardItem } from "./types"

interface Props {
  card: CardItem
  user: AuthUser
  busy: boolean
  variant: "normal" | "question"
  onApprove: (id: string) => void
  onReject: (id: string) => void
  onQuestion: (id: string) => void
  onDelete: (id: string) => void
  onEdit: (card: CardItem) => void
  onFilterByGroup: (groupId: string, groupName: string) => void
}

export default function DetailNormal({ card, user, busy, variant, onApprove, onReject, onQuestion, onDelete, onEdit, onFilterByGroup }: Props) {
  const id = String(card.id)
  const status = String(card.review_status || "")
  const canEdit = hasPermission(user, "knowledge.edit")
  const canApprove = hasPermission(user, "review.approve")
  const canReject = hasPermission(user, "review.reject")
  const canDelete = hasPermission(user, "knowledge.delete")
  const editorName = String(card.last_editor_name || "").trim()
  const editorId = String(card.last_editor_id || "").trim()
  const reviewerName = String(card.reviewed_by_name || card.reviewed_by || "").trim()
  const editCount = Number(card.edit_count || 0)
  const isOwnEdit = Boolean(editorId && editorId === user.id)
  const origin = variant === "question" ? questionOrigin(card) : null
  const parts = variant === "question" ? questionReviewParts(card) : null

  return (
    <div className={`rounded-xl border bg-content1/45 p-4 transition-colors ${cardBorderClass(status)}`}>
      {/* 头部：状态、ID、分类、答案类型、版本、来源标签等 */}
      <div className="mb-3 flex flex-wrap items-center gap-1.5">
        <span className={`inline-flex items-center rounded-md px-1.5 py-0.5 text-[0.65rem] font-semibold ${statusBadgeClass(status)}`}>
          {STATUS_LABEL[status] || status}
        </span>
        <span className="inline-flex h-5 min-w-5 items-center justify-center rounded-md bg-primary/15 px-1.5 text-[0.65rem] font-semibold text-primary">#{card.id}</span>
        {card.category && (
          <span className="rounded-md border border-white/10 bg-default-100/60 px-1.5 py-0.5 text-[0.65rem] font-semibold text-default-500">{card.category}</span>
        )}
        <span className="rounded-md border border-white/10 bg-default-100/60 px-1.5 py-0.5 text-[0.65rem] font-semibold text-default-500">
          {answerTypeLabel(card.answer_type)}
        </span>
        <span className="rounded-md border border-white/10 bg-default-100/60 px-1.5 py-0.5 text-[0.65rem] font-semibold text-default-500">
          {validStatusLabel(card.valid_status)}
        </span>
        {card.rlcraft_version && (
          <span className="rounded-md border border-warning/25 bg-warning/10 px-1.5 py-0.5 text-[0.65rem] font-semibold text-warning-foreground">
            版本 {card.rlcraft_version}
          </span>
        )}
        {origin && (
          <span className={`rounded-md border px-1.5 py-0.5 text-[0.65rem] font-semibold ${origin.className}`}>来源类型: {origin.label}</span>
        )}
        <span className="rounded-md border border-primary/20 bg-primary/10 px-1.5 py-0.5 text-[0.65rem] font-semibold text-primary">
          {variant === "question" ? "疑问人" : "修改人"}: {editorName || editorId || "系统/AI"}{isOwnEdit ? " (你)" : ""}
        </span>
        <span className="rounded-md border border-white/10 bg-default-100/60 px-1.5 py-0.5 text-[0.65rem] font-semibold text-default-500">
          编辑 {editCount} 次
        </span>
        {reviewerName && (
          <span className="rounded-md border border-success/25 bg-success/10 px-1.5 py-0.5 text-[0.65rem] font-semibold text-success">
            审核人: {reviewerName}
          </span>
        )}
      </div>

      {/* 标题 + 时间 */}
      <div className="mb-3 flex flex-wrap items-end justify-between gap-2 border-b border-white/5 pb-3">
        <div className="min-w-0 flex-1">
          <h3 className="text-base font-semibold leading-snug text-default-900">
            {card.title || (variant === "question" ? `疑问 #${card.id}` : card.question) || `卡片 #${card.id}`}
          </h3>
          {card.revision_of_card_id ? (
            <p className="mt-0.5 text-[0.7rem] text-warning-foreground">修订自 #{card.revision_of_card_id}</p>
          ) : null}
        </div>
        <div className="text-right text-[0.7rem] text-default-500">
          <div>{formatDate(card.created_at)}</div>
          {card.updated_at && card.updated_at !== card.created_at && (
            <div className="mt-0.5 text-default-400">更新于 {relativeTime(card.updated_at)}</div>
          )}
        </div>
      </div>

      <div className="grid gap-3">
        {/* 内容主体 */}
        {variant === "question" && parts ? (
          <>
            {parts.question && (
              <div className="rounded-md border border-white/10 bg-content1/45 px-3 py-2">
                <div className="mb-1 text-[0.65rem] font-semibold text-primary">Q</div>
                <p className="whitespace-pre-wrap text-sm leading-relaxed">{parts.question}</p>
              </div>
            )}
            {parts.reason && (
              <div className="rounded-md border border-warning/25 bg-warning/8 px-3 py-2">
                <div className="mb-1 flex items-center justify-between gap-2">
                  <span className="text-[0.65rem] font-semibold text-warning-foreground">疑问理由</span>
                  {parts.asker && <span className="text-[0.65rem] text-default-500">来自 {parts.asker}</span>}
                </div>
                <p className="whitespace-pre-wrap text-sm leading-relaxed text-default-700">{parts.reason}</p>
              </div>
            )}
            {parts.originalAnswer && (
              <details className="rounded-md border border-white/10 bg-content1/50 px-3 py-2 text-sm">
                <summary className="cursor-pointer select-none text-[0.65rem] font-semibold text-success">原答案摘要（点击展开）</summary>
                <p className="mt-1 whitespace-pre-wrap leading-relaxed text-default-600">{truncate(parts.originalAnswer, 1500)}</p>
              </details>
            )}
          </>
        ) : (
          card.question && (
            <div className="rounded-md border border-white/10 bg-content1/45 px-3 py-2">
              <div className="mb-1 text-[0.65rem] font-semibold text-primary">Q</div>
              <p className="whitespace-pre-wrap text-sm leading-relaxed">{card.question}</p>
            </div>
          )
        )}

        {card.answer && (
          <div className="rounded-md border border-white/10 bg-content1/50 px-3 py-2">
            <div className="mb-1 text-[0.65rem] font-semibold text-success">A</div>
            <p className="whitespace-pre-wrap text-sm leading-relaxed">{card.answer}</p>
          </div>
        )}

        {/* 数组字段 chips */}
        {(Array.isArray(card.search_terms) && card.search_terms.length > 0) || (Array.isArray(card.aliases) && card.aliases.length > 0) || (Array.isArray(card.tags) && card.tags.length > 0) ? (
          <div className="grid gap-2 text-xs">
            {Array.isArray(card.search_terms) && card.search_terms.length > 0 && (
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-[0.65rem] font-semibold text-default-500">检索关键词</span>
                {card.search_terms.map((value, idx) => (
                  <span key={`st-${idx}-${value}`} className="rounded-full border border-primary/15 bg-primary/8 px-2 py-0.5 text-[0.65rem] text-primary">
                    {String(value)}
                  </span>
                ))}
              </div>
            )}
            {Array.isArray(card.aliases) && card.aliases.length > 0 && (
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-[0.65rem] font-semibold text-default-500">别名</span>
                {card.aliases.map((value, idx) => (
                  <span key={`al-${idx}-${value}`} className="rounded-full border border-secondary/20 bg-secondary/10 px-2 py-0.5 text-[0.65rem] text-secondary">
                    {String(value)}
                  </span>
                ))}
              </div>
            )}
            {Array.isArray(card.tags) && card.tags.length > 0 && (
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-[0.65rem] font-semibold text-default-500">标签</span>
                {card.tags.map((value, idx) => (
                  <span key={`tg-${idx}-${value}`} className="rounded-full border border-white/10 bg-default-100/60 px-2 py-0.5 text-[0.65rem] text-default-500">
                    {String(value)}
                  </span>
                ))}
              </div>
            )}
          </div>
        ) : null}

        <AIVerdictCard card={card} />
        <SourceBlock card={card} onFilterByGroup={onFilterByGroup} />
        <RevisionDiff card={card} />

        {/* 原始 evidence 折叠 */}
        {card.evidence && variant !== "question" && (
          <details className="text-xs text-default-500">
            <summary className="cursor-pointer select-none hover:text-default-900">证据/来源说明（点击展开）</summary>
            <p className="mt-2 whitespace-pre-wrap rounded-md bg-default-100/40 p-2 text-[0.72rem] leading-relaxed">{card.evidence}</p>
          </details>
        )}

        {/* 操作区 */}
        <div className="flex flex-wrap items-center gap-1.5 border-t border-white/5 pt-3">
          {status === "processing" ? (
            <span className="inline-flex h-8 items-center gap-1.5 rounded-md border border-primary/25 bg-primary/10 px-2 text-xs font-semibold text-primary">
              <Loader2 className="h-3 w-3 animate-spin" />
              {PROCESSING_HINT}
            </span>
          ) : (
            <>
              {canEdit && (
                <button
                  type="button"
                  onClick={() => onEdit(card)}
                  disabled={busy}
                  className="inline-flex h-7 items-center gap-1 rounded-xl border border-white/10 bg-white/5 px-2.5 text-[0.7rem] font-semibold text-default-700 transition-colors hover:bg-white/10 hover:text-default-900 disabled:cursor-not-allowed disabled:opacity-50"
                  title={variant === "question" ? "打开编辑器补全 A 字段；保存后自动重新进入审核流程" : status === "approved" ? "已通过卡片不可原地编辑；保存会创建一份修订版" : "打开编辑器修改字段"}
                >
                  <Pencil className="h-3 w-3" />
                  {variant === "question" ? "补答案" : status === "approved" ? "新建修订" : "编辑"}
                </button>
              )}
              <ActionButton
                status={status}
                action="approve"
                onClick={() => onApprove(id)}
                busy={busy}
                disabledByPermission={!canApprove}
                isOwnEdit={isOwnEdit}
              />
              <ActionButton
                status={status}
                action="reject"
                onClick={() => onReject(id)}
                busy={busy}
                disabledByPermission={!canReject}
                isOwnEdit={isOwnEdit}
              />
              <ActionButton
                status={status}
                action="delete"
                onClick={() => onDelete(id)}
                busy={busy}
                disabledByPermission={!canDelete}
              />
            </>
          )}
        </div>
      </div>
    </div>
  )
}
