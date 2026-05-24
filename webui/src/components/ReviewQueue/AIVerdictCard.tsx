import type { CardItem } from "./types"

interface Props {
  card: CardItem
}

// 结构化展示后端的 ai_review_reason / ai_review_score / ai_review_issues。
// 替代以前在 evidence 文本上正则解析的方案。
export default function AIVerdictCard({ card }: Props) {
  const reason = String(card.ai_review_reason || "").trim()
  const score = typeof card.ai_review_score === "number" ? card.ai_review_score : null
  const issues = Array.isArray(card.ai_review_issues) ? card.ai_review_issues : []
  if (!reason && score == null && issues.length === 0) return null
  const status = String(card.ai_review_status || "")
  const isRejected = status === "ai_rejected" || status.includes("rejected")
  return (
    <div className={`rounded-lg border p-3 text-xs ${isRejected ? "border-destructive/25 bg-destructive/5" : "border-white/10 bg-default-100/35"}`}>
      <div className="mb-2 flex items-center justify-between gap-2">
        <span className={`text-[0.65rem] font-semibold ${isRejected ? "text-destructive" : "text-default-600"}`}>
          AI 评审 {status && <span className="ml-1 text-default-400">· {status}</span>}
        </span>
        {score != null && (
          <span className="inline-flex items-center gap-1.5">
            <span className="text-[0.65rem] text-default-500">评分</span>
            <span className="inline-flex h-1.5 w-20 overflow-hidden rounded-full bg-default-100/60">
              <span
                className={`h-full rounded-full ${score >= 0.7 ? "bg-success" : score >= 0.4 ? "bg-warning" : "bg-destructive"}`}
                style={{ width: `${Math.max(0, Math.min(1, score)) * 100}%` }}
              />
            </span>
            <span className="text-[0.7rem] font-semibold tabular-nums text-default-700">{score.toFixed(2)}</span>
          </span>
        )}
      </div>
      {reason && <p className="whitespace-pre-wrap leading-relaxed text-default-700">{reason}</p>}
      {issues.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {issues.map((issue, idx) => (
            <span
              key={`${issue}-${idx}`}
              className="inline-flex items-center rounded-full border border-destructive/20 bg-destructive/10 px-2 py-0.5 text-[0.65rem] font-medium text-destructive"
            >
              {issue}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
