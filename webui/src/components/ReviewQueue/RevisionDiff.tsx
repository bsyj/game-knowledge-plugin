import { useEffect, useState } from "react"
import { Loader2, ChevronDown } from "lucide-react"
import { fetchCard } from "@/lib/api"
import type { CardItem } from "./types"
import { diffLines, arrayDiff } from "./utils"
import { ANSWER_TYPE_OPTIONS, VALID_STATUS_OPTIONS } from "./constants"

const ANSWER_TYPE_MAP = Object.fromEntries(ANSWER_TYPE_OPTIONS.map((item) => [item.key, item.label]))
const VALID_STATUS_MAP = Object.fromEntries(VALID_STATUS_OPTIONS.map((item) => [item.key, item.label]))

interface Props {
  card: CardItem
}

const TEXT_FIELDS: { key: keyof CardItem; label: string; multiline?: boolean }[] = [
  { key: "title", label: "标题" },
  { key: "category", label: "分类" },
  { key: "answer_type", label: "答案类型" },
  { key: "valid_status", label: "有效状态" },
  { key: "rlcraft_version", label: "RLCraft 版本" },
  { key: "question", label: "Q", multiline: true },
  { key: "answer", label: "A", multiline: true },
  { key: "evidence", label: "证据/来源说明", multiline: true },
]

const ARRAY_FIELDS: { key: keyof CardItem; label: string }[] = [
  { key: "tags", label: "标签" },
  { key: "search_terms", label: "检索关键词" },
  { key: "aliases", label: "别名" },
]

function decorate(field: string, value: unknown): string {
  if (value == null) return ""
  const s = String(value)
  if (field === "answer_type") return ANSWER_TYPE_MAP[s] || s
  if (field === "valid_status") return VALID_STATUS_MAP[s] || s
  return s
}

export default function RevisionDiff({ card }: Props) {
  const baseId = card.revision_of_card_id
  const [open, setOpen] = useState(false)
  const [base, setBase] = useState<CardItem | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open || !baseId || base || loading) return
    setLoading(true)
    setError(null)
    fetchCard(String(baseId))
      .then((data) => {
        const result = data as { card?: CardItem }
        if (result?.card) setBase(result.card)
        else setError("原卡片不存在")
      })
      .catch(() => setError("加载原卡失败"))
      .finally(() => setLoading(false))
  }, [open, baseId, base, loading])

  if (!baseId) return null

  return (
    <div className="rounded-lg border border-warning/25 bg-warning/5 p-3 text-xs">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-center justify-between gap-2 text-left"
      >
        <span className="text-[0.7rem] font-semibold text-warning-foreground">
          修订自 #{baseId} · {open ? "收起对比" : "展开字段对比"}
        </span>
        <ChevronDown className={`h-3.5 w-3.5 text-warning-foreground transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div className="mt-2">
          {loading && (
            <div className="flex items-center gap-2 text-default-500">
              <Loader2 className="h-3 w-3 animate-spin" />
              加载原卡…
            </div>
          )}
          {error && <p className="text-destructive">{error}</p>}
          {base && (
            <div className="grid gap-2">
              {TEXT_FIELDS.map(({ key, label, multiline }) => {
                const oldVal = decorate(String(key), base[key])
                const newVal = decorate(String(key), card[key])
                if (oldVal === newVal) return null
                if (multiline) {
                  return (
                    <div key={String(key)} className="rounded-md border border-white/10 bg-content1/40 p-2">
                      <div className="mb-1 text-[0.62rem] font-semibold text-default-500">{label}</div>
                      <div className="space-y-0.5 font-mono text-[0.7rem] leading-relaxed">
                        {diffLines(oldVal, newVal).map((line, idx) => (
                          <div
                            key={idx}
                            className={
                              line.kind === "add"
                                ? "rounded bg-success/12 px-1.5 text-success"
                                : line.kind === "del"
                                  ? "rounded bg-destructive/10 px-1.5 text-destructive line-through"
                                  : "px-1.5 text-default-500"
                            }
                          >
                            <span className="mr-1 text-default-400">{line.kind === "add" ? "+" : line.kind === "del" ? "-" : " "}</span>
                            {line.text || " "}
                          </div>
                        ))}
                      </div>
                    </div>
                  )
                }
                return (
                  <div key={String(key)} className="grid grid-cols-[5rem_1fr] items-start gap-2 rounded-md border border-white/10 bg-content1/40 p-2">
                    <div className="text-[0.62rem] font-semibold text-default-500">{label}</div>
                    <div className="text-[0.7rem] leading-relaxed">
                      <span className="rounded bg-destructive/10 px-1.5 py-0.5 text-destructive line-through">{oldVal || "—"}</span>
                      <span className="mx-1.5 text-default-400">→</span>
                      <span className="rounded bg-success/12 px-1.5 py-0.5 text-success">{newVal || "—"}</span>
                    </div>
                  </div>
                )
              })}
              {ARRAY_FIELDS.map(({ key, label }) => {
                const diff = arrayDiff(base[key], card[key])
                if (diff.added.length === 0 && diff.removed.length === 0) return null
                return (
                  <div key={String(key)} className="rounded-md border border-white/10 bg-content1/40 p-2">
                    <div className="mb-1 text-[0.62rem] font-semibold text-default-500">{label}</div>
                    <div className="flex flex-wrap gap-1.5">
                      {diff.removed.map((value) => (
                        <span key={`del-${value}`} className="rounded-full border border-destructive/20 bg-destructive/10 px-2 py-0.5 text-[0.65rem] text-destructive line-through">
                          {value}
                        </span>
                      ))}
                      {diff.added.map((value) => (
                        <span key={`add-${value}`} className="rounded-full border border-success/25 bg-success/10 px-2 py-0.5 text-[0.65rem] text-success">
                          {value}
                        </span>
                      ))}
                    </div>
                  </div>
                )
              })}
              {TEXT_FIELDS.every(({ key }) => decorate(String(key), base[key]) === decorate(String(key), card[key])) &&
                ARRAY_FIELDS.every(({ key }) => {
                  const d = arrayDiff(base[key], card[key])
                  return d.added.length === 0 && d.removed.length === 0
                }) && <p className="text-default-500">没有可见的字段差异（可能仅元数据变化）</p>}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
