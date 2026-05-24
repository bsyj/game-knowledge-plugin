import type { CardItem } from "./types"
import { ANSWER_TYPE_OPTIONS, VALID_STATUS_OPTIONS, STATUS_LABEL } from "./constants"

export function statusBadgeClass(status: string) {
  if (status === "pending") return "bg-warning text-warning-foreground"
  if (status === "needs_answer") return "bg-primary/15 text-primary"
  if (status === "similar") return "bg-secondary text-secondary-foreground"
  if (status === "conflict") return "bg-warning/20 text-warning-foreground"
  if (status === "processing") return "bg-primary text-primary-foreground"
  if (status === "approved") return "bg-success text-success-foreground"
  if (status === "ai_rejected") return "bg-destructive/15 text-destructive"
  if (status === "rejected") return "bg-destructive text-destructive-foreground"
  if (status === "superseded") return "bg-default-100/60 text-default-500"
  return "bg-default-100/60 text-default-500"
}

export function cardBorderClass(status: string) {
  if (status === "needs_answer") return "border-primary/40"
  if (status === "similar") return "border-secondary/60"
  if (status === "conflict") return "border-warning/60"
  if (status === "processing") return "border-primary/50"
  if (status === "approved") return "border-success/50"
  if (status === "ai_rejected") return "border-destructive/50"
  if (status === "rejected") return "border-warning/50"
  return "border-white/10"
}

export function similarStatusHint(status?: string) {
  const value = String(status || "").trim()
  if (value === "approved") return "已在库中"
  if (value === "needs_answer") return "疑问"
  if (value === "similar") return "也在判重"
  if (value === "conflict") return "冲突待确认"
  if (value === "ai_rejected") return "AI已拒绝"
  if (value === "superseded") return "已被替代"
  return STATUS_LABEL[value] || value || "未知状态"
}

export function similarColumnClass(status?: string, isCurrent = false) {
  if (isCurrent) return "bg-secondary/10"
  const value = String(status || "")
  if (value === "approved") return "bg-success/8"
  if (value === "needs_answer") return "bg-primary/8"
  if (value === "ai_rejected") return "bg-destructive/8"
  if (value === "conflict") return "bg-warning/10"
  if (value === "superseded") return "bg-default-100/35 opacity-75"
  return "bg-content1/55"
}

export function answerTypeLabel(value?: string) {
  const token = String(value || "other").trim()
  return ANSWER_TYPE_OPTIONS.find((item) => item.key === token)?.label || token
}

export function validStatusLabel(value?: string) {
  const token = String(value || "active").trim()
  return VALID_STATUS_OPTIONS.find((item) => item.key === token)?.label || token
}

export function listToText(value?: unknown): string {
  return Array.isArray(value) ? value.map((item) => String(item || "").trim()).filter(Boolean).join(", ") : ""
}

export function splitEditList(value: string): string[] {
  return value.split(/[,\n，、;；]+/).map((item) => item.trim()).filter(Boolean)
}

export function apiErrorMessage(error: unknown, fallback: string) {
  if (typeof error === "object" && error && "response" in error) {
    const detail = (error as { response?: { data?: { error?: string } } }).response?.data?.error
    if (detail) return String(detail)
  }
  return error instanceof Error ? error.message : fallback
}

export function isQuestionCard(card: CardItem) {
  const tags = Array.isArray(card.tags) ? card.tags : []
  const evidence = String(card.evidence || "")
  const aiStatus = String(card.ai_review_status || "")
  return (
    aiStatus === "manual_question" ||
    aiStatus === "manual_review_question" ||
    tags.includes("疑问") ||
    evidence.includes("疑问理由:") ||
    evidence.includes("疑问人:") ||
    evidence.includes("人工标疑:")
  )
}

// 优先使用结构化字段，evidence 文本仅作兜底
export function questionReviewParts(card: CardItem) {
  const rawQuestion = String(card.question || "").trim()
  const rawEvidence = String(card.evidence || "").trim()
  const rawReason = String(card.ai_review_reason || "").trim()
  let question = rawQuestion
  let reason = ""
  const marker = "\n\n原问题:"
  const markerIndex = rawQuestion.indexOf(marker)
  if (markerIndex >= 0) {
    reason = rawQuestion.slice(0, markerIndex).trim()
    question = rawQuestion.slice(markerIndex + marker.length).trim()
  }
  if (!reason) {
    reason = rawEvidence.match(/(?:^|\n)疑问理由[:：]\s*([\s\S]*?)(?=\n(?:疑问人|来源检索|原问题|原答案摘要|人工标疑)[:：]|$)/)?.[1]?.trim() || ""
  }
  if (!reason && rawReason && !/对检索结果提出疑问/.test(rawReason)) reason = rawReason
  const originalQuestion = rawEvidence.match(/(?:^|\n)原问题[:：]\s*([^\n]+)/)?.[1]?.trim() || ""
  if (originalQuestion) question = originalQuestion
  const originalAnswer = rawEvidence.match(/(?:^|\n)原答案摘要[:：]\s*([\s\S]*?)(?=\n(?:疑问人|来源检索|原问题|人工标疑)[:：]|$)/)?.[1]?.trim() || ""
  const askerFromEvidence =
    rawEvidence.match(/(?:^|\n)疑问人[:：]\s*([^\n]+)/)?.[1]?.trim()
    || rawEvidence.match(/(?:^|\n)人工标疑[:：]\s*([^\n]+)/)?.[1]?.trim()
    || ""
  return { question, reason, originalAnswer, asker: askerFromEvidence }
}

export function questionOrigin(card: CardItem) {
  const aiStatus = String(card.ai_review_status || "").trim()
  if (aiStatus === "manual_review_question") {
    return { label: "审核员标疑（未入库）", className: "border-warning/40 bg-warning/15 text-warning-foreground" }
  }
  if (aiStatus === "manual_question") {
    return { label: "检索疑问", className: "border-primary/25 bg-primary/10 text-primary" }
  }
  if (aiStatus.startsWith("tuning_")) {
    return { label: "随机调优", className: "border-warning/30 bg-warning/10 text-warning-foreground" }
  }
  return { label: "系统/AI自动", className: "border-secondary/25 bg-secondary/10 text-secondary-foreground" }
}

// 简易行级 LCS diff，用于修订对比
export type DiffLine = { kind: "same" | "add" | "del"; text: string }

export function diffLines(oldText: string, newText: string): DiffLine[] {
  const o = oldText.split(/\r?\n/)
  const n = newText.split(/\r?\n/)
  const m = o.length
  const k = n.length
  const lcs: number[][] = Array.from({ length: m + 1 }, () => new Array(k + 1).fill(0))
  for (let i = m - 1; i >= 0; i--) {
    for (let j = k - 1; j >= 0; j--) {
      if (o[i] === n[j]) lcs[i][j] = lcs[i + 1][j + 1] + 1
      else lcs[i][j] = Math.max(lcs[i + 1][j], lcs[i][j + 1])
    }
  }
  const out: DiffLine[] = []
  let i = 0
  let j = 0
  while (i < m && j < k) {
    if (o[i] === n[j]) {
      out.push({ kind: "same", text: o[i] })
      i++
      j++
    } else if (lcs[i + 1][j] >= lcs[i][j + 1]) {
      out.push({ kind: "del", text: o[i] })
      i++
    } else {
      out.push({ kind: "add", text: n[j] })
      j++
    }
  }
  while (i < m) out.push({ kind: "del", text: o[i++] })
  while (j < k) out.push({ kind: "add", text: n[j++] })
  return out
}

export function arrayDiff(oldArr?: unknown, newArr?: unknown) {
  const o = new Set(Array.isArray(oldArr) ? oldArr.map((x) => String(x)) : [])
  const n = new Set(Array.isArray(newArr) ? newArr.map((x) => String(x)) : [])
  const added: string[] = []
  const removed: string[] = []
  const kept: string[] = []
  n.forEach((v) => (o.has(v) ? kept.push(v) : added.push(v)))
  o.forEach((v) => {
    if (!n.has(v)) removed.push(v)
  })
  return { added, removed, kept }
}

export function relativeTime(ts?: number) {
  if (!ts) return "-"
  const value = ts > 0 && ts < 1_000_000_000_000 ? ts * 1000 : ts
  const diff = Date.now() - value
  if (diff < 0) return "刚刚"
  const sec = Math.floor(diff / 1000)
  if (sec < 60) return `${sec} 秒前`
  const min = Math.floor(sec / 60)
  if (min < 60) return `${min} 分钟前`
  const hour = Math.floor(min / 60)
  if (hour < 24) return `${hour} 小时前`
  const day = Math.floor(hour / 24)
  if (day < 30) return `${day} 天前`
  const month = Math.floor(day / 30)
  if (month < 12) return `${month} 个月前`
  return `${Math.floor(month / 12)} 年前`
}
