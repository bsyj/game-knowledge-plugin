import { useMemo, useState } from "react"
import { createPortal } from "react-dom"
import { BookOpen, CircleHelp, Database, GitBranch, Hash, Layers3, Pencil, Save, Search, Shuffle, SlidersHorizontal, Trash2, X } from "lucide-react"
import { createGraphEdge, deleteGraphEdge, deleteSearchHit, fetchSearchHitCard, hasPermission, questionSearchHit, randomSearchMemory, searchMemory, updateSearchHit, type AuthUser } from "@/lib/api"
import { useToast } from "@/components/Toast"
import Card from "@/components/Card"
import Button from "@/components/Button"
import Loading from "@/components/Loading"
import { formatDate, truncate } from "@/lib/utils"

type SearchHit = {
  hash?: string
  id?: string
  type?: string
  source?: string
  content?: string
  title?: string
  score?: number
  metadata?: Record<string, unknown>
  [key: string]: unknown
}

type SearchPayload = {
  summary?: string
  hits?: SearchHit[]
  results?: SearchHit[]
  count?: number
  error?: string
  filtered?: boolean
}

const SEARCH_MODES = [
  { key: "aggregate", label: "综合" },
  { key: "search", label: "语义" },
  { key: "time", label: "时间" },
]

const CATEGORY_OPTIONS = ["攻略", "机制", "推荐", "配置", "报错", "装备", "版本", "模组", "掉落", "位置", "其他"]
const ANSWER_TYPE_OPTIONS = [
  { key: "error_fix", label: "报错修复" },
  { key: "config", label: "配置" },
  { key: "recommendation", label: "推荐" },
  { key: "guide", label: "攻略" },
  { key: "mechanic", label: "机制" },
  { key: "location", label: "位置" },
  { key: "drop", label: "掉落" },
  { key: "other", label: "其他" },
]
const VALID_STATUS_OPTIONS = [
  { key: "active", label: "有效" },
  { key: "stale", label: "待更新" },
  { key: "deprecated", label: "已过期" },
  { key: "conflict", label: "冲突" },
]

const MODE_HINT: Record<string, string> = {
  aggregate: "综合",
  search: "语义",
  time: "时间",
}

const RESULT_BORDER = "rounded-xl border border-white/10 bg-content1/45 p-3"
const RELATION_RESULT_BORDER = "rounded-xl border border-sky-400/45 bg-sky-500/8 p-3 shadow-[inset_3px_0_0_rgb(56_189_248_/_0.75)]"
const TOOL_INPUT = "napcat-input h-8 rounded-md px-2 text-xs transition-colors"
const EDIT_INPUT = "napcat-input w-full rounded-md px-2 py-1.5 text-sm transition-colors"
const MAX_SEARCH_QUERY_LENGTH = 500

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {}
}

function asText(value: unknown): string {
  if (value == null) return ""
  if (Array.isArray(value)) return value.map(asText).filter(Boolean).join("、")
  if (typeof value === "object") return JSON.stringify(value)
  return String(value)
}

function asStringList(value: unknown): string[] {
  if (Array.isArray(value)) return value.map(asText).map((item) => item.trim()).filter(Boolean)
  const text = asText(value)
  return text ? text.split(/[,\n，、;；]+/).map((item) => item.trim()).filter(Boolean) : []
}

function listToText(value: unknown): string {
  return asStringList(value).join(", ")
}

function splitEditList(value: string): string[] {
  return value.split(/[,\n，、;；]+/).map((item) => item.trim()).filter(Boolean)
}

function answerTypeLabel(value: unknown): string {
  const token = asText(value || "other").trim()
  return ANSWER_TYPE_OPTIONS.find((item) => item.key === token)?.label || token
}

function validStatusLabel(value: unknown): string {
  const token = asText(value || "active").trim()
  return VALID_STATUS_OPTIONS.find((item) => item.key === token)?.label || token
}

function asNumber(value: unknown): number | undefined {
  const numeric = typeof value === "number" ? value : Number(value)
  return Number.isFinite(numeric) ? numeric : undefined
}

function errorMessage(error: unknown, fallback: string): string {
  const err = asRecord(error)
  const response = asRecord(err.response)
  const data = asRecord(response.data)
  const status = asText(response.status)
  const detail = asText(data.error || data.message || err.message)
  if (status && detail) return `${fallback}: ${status} ${detail}`
  if (detail) return `${fallback}: ${detail}`
  return fallback
}

function normalizePayload(raw: unknown): SearchPayload {
  const payload = asRecord(raw)
  const hits = Array.isArray(payload.hits)
    ? payload.hits
    : Array.isArray(payload.results)
      ? payload.results
      : []
  return {
    summary: asText(payload.summary),
    hits: hits.map((item) => asRecord(item) as SearchHit),
    count: asNumber(payload.count) ?? hits.length,
    error: asText(payload.error),
    filtered: Boolean(payload.filtered),
  }
}

function extractQA(hit: SearchHit) {
  const metadata = asRecord(hit.metadata)
  const content = asText(hit.content)
  const title = asText(metadata.title || hit.title).trim()
  const question = asText(metadata.question).trim() || matchLine(content, /(?:^|\n)\s*Q[:：]\s*([^\n]+)/i)
  const answer = matchBlock(content, /(?:^|\n)\s*A[:：]\s*([\s\S]*?)(?=\n\s*(?:标签|证据|步骤)[:：]|\n\s*Q[:：]|$)/i)
  const fallbackTitle = title || firstUsefulLine(content)
  return {
    title: fallbackTitle,
    question,
    answer: answer || (question ? "" : content),
  }
}

function extractDetails(hit: SearchHit) {
  const metadata = asRecord(hit.metadata)
  const content = asText(hit.content)
  const stepsFromMeta = Array.isArray(metadata.steps) ? metadata.steps.map(asText).filter(Boolean) : []
  const tagsFromMeta = Array.isArray(metadata.tags) ? metadata.tags.map(asText).filter(Boolean).join(", ") : asText(metadata.tags)
  return {
    steps: stepsFromMeta.length > 0 ? stepsFromMeta.join("\n") : extractSteps(content).join("\n"),
    tags: tagsFromMeta || matchLine(content, /(?:^|\n)\s*标签[:：]\s*([^\n]+)/),
    search_terms: listToText(metadata.search_terms),
    aliases: listToText(metadata.aliases),
    rlcraft_version: asText(metadata.rlcraft_version),
    answer_type: asText(metadata.answer_type || "other"),
    valid_status: asText(metadata.valid_status || "active"),
    evidence: asText(metadata.evidence) || matchBlock(content, /(?:^|\n)\s*证据[:：]\s*([\s\S]*?)$/),
  }
}

function extractSteps(text: string): string[] {
  const block = matchBlock(text, /(?:^|\n)\s*步骤[:：]\s*([\s\S]*?)(?=\n\s*(?:标签|证据)[:：]|$)/)
  if (!block) return []
  return block
    .split(/\r?\n/)
    .map((line) => line.replace(/^\s*\d+[.、)]\s*/, "").trim())
    .filter(Boolean)
}

function matchLine(text: string, pattern: RegExp): string {
  return (text.match(pattern)?.[1] || "").trim()
}

function matchBlock(text: string, pattern: RegExp): string {
  return (text.match(pattern)?.[1] || "").trim()
}

function firstUsefulLine(text: string): string {
  return text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .find((line) => line && !/^[QA][:：]/i.test(line)) || "未命名知识"
}

function metaLine(hit: SearchHit): string[] {
  const metadata = asRecord(hit.metadata)
  return [
    asText(metadata.category).trim(),
    asText(metadata.rlcraft_version).trim() ? `版本: ${asText(metadata.rlcraft_version).trim()}` : "",
  ].filter(Boolean)
}

function resultTypeLabel(hit: SearchHit): string {
  const source = asText(hit.source).trim()
  const type = asText(hit.type).trim()
  if (type === "relation") return "图谱关系"
  if (source === "metadata_question_fallback") return "元数据命中"
  if (source === "anchor_fts_fallback") return "关键词命中"
  return MODE_HINT[type] || type || source || "结果"
}

function isRelationHit(hit: SearchHit): boolean {
  return asText(hit.type).trim().toLowerCase() === "relation"
}

type RelationEditForm = {
  subject: string
  predicate: string
  object: string
  weight: string
}

function relationFormFromHit(hit: SearchHit): RelationEditForm {
  const metadata = asRecord(hit.metadata)
  const contentParts = asText(hit.content || hit.title).trim().split(/\s+/).filter(Boolean)
  const subject = asText(hit.subject || metadata.subject || metadata.source || contentParts[0]).trim()
  const object = asText(hit.object || metadata.object || metadata.target || contentParts[contentParts.length - 1]).trim()
  const middle = contentParts.length >= 3 ? contentParts.slice(1, -1).join(" ") : ""
  const predicate = asText(hit.predicate || metadata.predicate || metadata.label || middle || "关联").trim()
  const weightValue = asNumber(hit.weight ?? hit.confidence ?? metadata.weight ?? metadata.confidence)
  return {
    subject,
    predicate,
    object,
    weight: weightValue == null || weightValue <= 0 ? "1" : String(Number(weightValue.toFixed(4))),
  }
}

function scoreLabel(score: unknown): string {
  const numeric = asNumber(score)
  if (numeric == null) return ""
  return numeric >= 10 ? numeric.toFixed(1) : numeric.toFixed(3)
}

function displayScore(hit: SearchHit): { rank: string; raw: string } {
  const metadata = asRecord(hit.metadata)
  return {
    rank: scoreLabel(hit.rank_score ?? metadata.rank_score ?? hit.score),
    raw: scoreLabel(hit.score),
  }
}

function hashShort(hit: SearchHit): string {
  const hash = hitHash(hit)
  return hash ? hash.slice(0, 10) : ""
}

function paragraphHash(hit: SearchHit): string {
  const metadata = asRecord(hit.metadata)
  return asText(
    hit.paragraph_hash
    || metadata.paragraph_hash
    || metadata.paragraph_id
  ).trim()
}

function hitHash(hit: SearchHit): string {
  const metadata = asRecord(hit.metadata)
  return asText(
    paragraphHash(hit)
    || hit.hash
    || hit.id
    || hit.hash_value
    || metadata.hash,
  ).trim()
}

function eventTime(hit: SearchHit): string {
  const metadata = asRecord(hit.metadata)
  const value = metadata.event_time_start || metadata.created_at || metadata.time
  return value == null || value === "" ? "" : formatDate(value as string | number)
}

function editCount(hit: SearchHit): number {
  const metadata = asRecord(hit.metadata)
  const value = asNumber(hit.edit_count ?? metadata.edit_count)
  return value == null ? 0 : Math.max(0, Math.floor(value))
}

interface SearchEditorProps {
  hit: SearchHit
  editForm: {
    title: string
    category: string
    question: string
    answer: string
    steps: string
    search_terms: string
    aliases: string
    rlcraft_version: string
    answer_type: string
    valid_status: string
    evidence: string
  }
  busy: boolean
  onChange: (key: keyof SearchEditorProps["editForm"], value: string) => void
  onClose: () => void
  onSave: () => void
}

function SearchEditor({ hit, editForm, busy, onChange, onClose, onSave }: SearchEditorProps) {
  const relationHit = isRelationHit(hit)
  const relationText = asText(hit.content || hit.title).trim()
  const shellClass = relationHit
    ? "gk-modal-panel flex max-h-[calc(100dvh-2rem)] w-full max-w-3xl flex-col overflow-hidden rounded-2xl ring-1 ring-sky-400/30 md:max-h-[calc(100dvh-3rem)]"
    : "gk-modal-panel flex max-h-[calc(100dvh-2rem)] w-full max-w-3xl flex-col overflow-hidden rounded-2xl md:max-h-[calc(100dvh-3rem)]"
  return createPortal(
    <div className="gk-modal-overlay fixed inset-0 z-[9999] flex items-center justify-center p-3 md:p-6">
      <div className={shellClass}>
        <div className={`gk-modal-header flex shrink-0 items-start justify-between gap-3 border-b px-4 py-3 ${relationHit ? "bg-sky-500/8" : ""}`}>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-sm font-semibold">{relationHit ? "编辑图谱关系命中" : "编辑检索结果"}</h3>
              {relationHit && (
                <span className="inline-flex items-center gap-1 rounded-md border border-sky-400/40 bg-sky-500/15 px-1.5 py-0.5 text-[0.65rem] font-semibold text-sky-700 dark:text-sky-200">
                  <GitBranch className="h-3 w-3" />图谱关系
                </span>
              )}
            </div>
            <p className="mt-0.5 text-xs text-default-500">
              {relationHit ? "保存会基于这条关系创建待审核知识卡，不会直接改动图谱边" : "保存后会生成待审核修订版，通过后才写入知识库"}
            </p>
          </div>
          <Button variant="ghost" size="sm" onClick={onClose}><X className="h-3 w-3" /></Button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
          <div className="grid gap-3">
            {relationHit && (
              <div className="gk-modal-surface rounded-xl p-3 text-xs text-sky-900 dark:text-sky-100">
                <div className="mb-1 flex items-center gap-1.5 font-semibold">
                  <GitBranch className="h-3.5 w-3.5" />原始图谱关系
                </div>
                <p className="whitespace-pre-wrap leading-relaxed">{relationText || "无关系文本"}</p>
              </div>
            )}
            <label className="grid gap-1 text-xs text-default-500">
              标题
              <input className={EDIT_INPUT} value={editForm.title} onChange={(event) => onChange("title", event.target.value)} />
            </label>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="grid gap-1 text-xs text-default-500">
                分类
                <select className={EDIT_INPUT} value={editForm.category} onChange={(event) => onChange("category", event.target.value)}>
                  <option value="">未分类</option>
                  {CATEGORY_OPTIONS.map((item) => <option key={item} value={item}>{item}</option>)}
                </select>
              </label>
              <label className="grid gap-1 text-xs text-default-500">
                游戏版本
                <input className={EDIT_INPUT} value={editForm.rlcraft_version} onChange={(event) => onChange("rlcraft_version", event.target.value)} placeholder="例如 2.9 / 3.3 / 当前服版本" />
              </label>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="grid gap-1 text-xs text-default-500">
                答案类型
                <select className={EDIT_INPUT} value={editForm.answer_type} onChange={(event) => onChange("answer_type", event.target.value)}>
                  {ANSWER_TYPE_OPTIONS.map((item) => <option key={item.key} value={item.key}>{item.label}</option>)}
                </select>
              </label>
              <label className="grid gap-1 text-xs text-default-500">
                有效状态
                <select className={EDIT_INPUT} value={editForm.valid_status} onChange={(event) => onChange("valid_status", event.target.value)}>
                  {VALID_STATUS_OPTIONS.map((item) => <option key={item.key} value={item.key}>{item.label}</option>)}
                </select>
              </label>
            </div>
            <label className="grid gap-1 text-xs text-default-500">
              Q
              <textarea className={`${EDIT_INPUT} min-h-24 resize-y`} value={editForm.question} onChange={(event) => onChange("question", event.target.value)} />
            </label>
            <label className="grid gap-1 text-xs text-default-500">
              A
              <textarea className={`${EDIT_INPUT} min-h-36 resize-y`} value={editForm.answer} onChange={(event) => onChange("answer", event.target.value)} />
            </label>
            <label className="grid gap-1 text-xs text-default-500">
              步骤
              <textarea className={`${EDIT_INPUT} min-h-24 resize-y`} value={editForm.steps} onChange={(event) => onChange("steps", event.target.value)} placeholder="每行一个步骤" />
            </label>
            <label className="grid gap-1 text-xs text-default-500">
              检索关键词
              <textarea className={`${EDIT_INPUT} min-h-20 resize-y`} value={editForm.search_terms} onChange={(event) => onChange("search_terms", event.target.value)} placeholder="物品、附魔、boss、报错原文、配置项、群内简称" />
            </label>
            <label className="grid gap-1 text-xs text-default-500">
              别名
              <input className={EDIT_INPUT} value={editForm.aliases} onChange={(event) => onChange("aliases", event.target.value)} placeholder="游戏名、简称、俗称等" />
            </label>
            <label className="grid gap-1 text-xs text-default-500">
              证据/来源说明
              <textarea className={`${EDIT_INPUT} min-h-20 resize-y`} value={editForm.evidence} onChange={(event) => onChange("evidence", event.target.value)} />
            </label>
          </div>
        </div>
        <div className="gk-modal-footer flex shrink-0 justify-end gap-2 border-t px-4 py-3">
          <Button variant="outline" size="sm" onClick={onClose}>取消</Button>
          <Button variant="primary" size="sm" onClick={onSave} disabled={busy}>
            <Save className="h-3 w-3" />保存
          </Button>
        </div>
      </div>
    </div>,
    document.body,
  )
}

interface RelationEditorProps {
  hit: SearchHit
  form: RelationEditForm
  busy: boolean
  onChange: (key: keyof RelationEditForm, value: string) => void
  onClose: () => void
  onSave: () => void
}

function RelationEditor({ hit, form, busy, onChange, onClose, onSave }: RelationEditorProps) {
  const original = relationFormFromHit(hit)
  const shortHash = hashShort(hit)
  return createPortal(
    <div className="gk-modal-overlay fixed inset-0 z-[9999] flex items-center justify-center p-3 md:p-6">
      <div className="gk-modal-panel w-full max-w-2xl overflow-hidden rounded-2xl">
        <div className="gk-modal-header border-b border-sky-400/30 bg-sky-500/10 px-4 py-3">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-sm font-semibold">图谱关系编辑</h3>
                <span className="inline-flex items-center gap-1 rounded-md border border-sky-400/40 bg-sky-500/15 px-1.5 py-0.5 text-[0.65rem] font-semibold text-sky-700 dark:text-sky-200">
                  <GitBranch className="h-3 w-3" />relation
                </span>
                {shortHash && <span className="text-[0.68rem] text-default-500">#{shortHash}</span>}
              </div>
              <p className="mt-0.5 text-xs text-default-500">保存会创建新图谱边，并删除原关系；不进入知识卡审核队列。</p>
            </div>
            <Button variant="ghost" size="sm" onClick={onClose}><X className="h-3 w-3" /></Button>
          </div>
        </div>

        <div className="space-y-4 px-4 py-4">
          <div className="gk-modal-surface rounded-xl p-3">
            <div className="mb-2 text-[0.68rem] font-semibold uppercase tracking-wide text-sky-700 dark:text-sky-200">原关系</div>
            <div className="grid gap-2 text-sm sm:grid-cols-[1fr_auto_1fr] sm:items-center">
              <div className="rounded-lg border border-sky-400/25 bg-[var(--gk-input-bg)] px-3 py-2 font-medium">{original.subject || "未识别主体"}</div>
              <div className="rounded-full border border-sky-400/35 bg-sky-500/15 px-3 py-1 text-center text-xs font-semibold text-sky-700 dark:text-sky-200">{original.predicate || "关联"}</div>
              <div className="rounded-lg border border-sky-400/25 bg-[var(--gk-input-bg)] px-3 py-2 font-medium">{original.object || "未识别客体"}</div>
            </div>
          </div>

          <div className="grid gap-3">
            <label className="grid gap-1 text-xs text-default-500">
              主体
              <input className={EDIT_INPUT} value={form.subject} onChange={(event) => onChange("subject", event.target.value)} placeholder="例如 银套" />
            </label>
            <label className="grid gap-1 text-xs text-default-500">
              关系
              <input className={EDIT_INPUT} value={form.predicate} onChange={(event) => onChange("predicate", event.target.value)} placeholder="例如 免疫 / 掉落 / 位于 / 需要" />
            </label>
            <label className="grid gap-1 text-xs text-default-500">
              客体
              <input className={EDIT_INPUT} value={form.object} onChange={(event) => onChange("object", event.target.value)} placeholder="例如 寄巢之唤" />
            </label>
            <label className="grid gap-1 text-xs text-default-500">
              权重
              <input className={EDIT_INPUT} value={form.weight} onChange={(event) => onChange("weight", event.target.value)} placeholder="0.1 - 1.0" />
            </label>
          </div>
        </div>

        <div className="gk-modal-footer flex justify-end gap-2 border-t border-sky-400/25 px-4 py-3">
          <Button variant="outline" size="sm" onClick={onClose}>取消</Button>
          <Button variant="primary" size="sm" onClick={onSave} disabled={busy || !form.subject.trim() || !form.predicate.trim() || !form.object.trim()}>
            <Save className="h-3 w-3" />保存图谱关系
          </Button>
        </div>
      </div>
    </div>,
    document.body,
  )
}

interface QuestionDialogProps {
  hit: SearchHit
  value: string
  busy: boolean
  onChange: (value: string) => void
  onClose: () => void
  onSubmit: () => void
}

function QuestionDialog({ hit, value, busy, onChange, onClose, onSubmit }: QuestionDialogProps) {
  const qa = extractQA(hit)
  return createPortal(
    <div className="gk-modal-overlay fixed inset-0 z-[9999] flex items-center justify-center p-3 md:p-6">
      <div className="gk-modal-panel w-full max-w-2xl overflow-hidden rounded-2xl">
        <div className="gk-modal-header flex items-start justify-between gap-3 border-b px-4 py-3">
          <div>
            <h3 className="text-sm font-semibold">提交疑问</h3>
            <p className="mt-0.5 text-xs text-default-500">会进入审核队列的疑问分组，并记录疑问人</p>
          </div>
          <Button variant="ghost" size="sm" onClick={onClose}><X className="h-3 w-3" /></Button>
        </div>
        <div className="space-y-3 px-4 py-3">
          <div className="gk-modal-surface rounded-lg p-2.5">
            <div className="text-xs font-semibold text-default-900">{qa.title}</div>
            {qa.question && <p className="mt-1 text-xs text-default-500">Q: {truncate(qa.question, 180)}</p>}
            {qa.answer && <p className="mt-1 text-xs text-default-500">A: {truncate(qa.answer, 260)}</p>}
          </div>
          <label className="grid gap-1 text-xs text-default-500">
            疑问理由
            <textarea
              className={`${EDIT_INPUT} min-h-32 resize-y`}
              value={value}
              onChange={(event) => onChange(event.target.value)}
              placeholder="写清楚哪里不对、哪里缺答案，或你希望审核员补充什么"
            />
          </label>
        </div>
        <div className="gk-modal-footer flex justify-end gap-2 border-t px-4 py-3">
          <Button variant="outline" size="sm" onClick={onClose}>取消</Button>
          <Button variant="primary" size="sm" onClick={onSubmit} disabled={busy || !value.trim()}>
            <CircleHelp className="h-3 w-3" />提交疑问
          </Button>
        </div>
      </div>
    </div>,
    document.body,
  )
}

export default function SearchPanel({ user }: { user: AuthUser }) {
  const { toast } = useToast()
  const [query, setQuery] = useState("")
  const [mode, setMode] = useState("aggregate")
  const [limit, setLimit] = useState(12)
  const [result, setResult] = useState<SearchPayload | null>(null)
  const [loading, setLoading] = useState(false)
  const [busyHash, setBusyHash] = useState("")
  const [editingHit, setEditingHit] = useState<SearchHit | null>(null)
  const [editingRelationHit, setEditingRelationHit] = useState<SearchHit | null>(null)
  const [questionHit, setQuestionHit] = useState<SearchHit | null>(null)
  const [questionText, setQuestionText] = useState("")
  const [relationForm, setRelationForm] = useState<RelationEditForm>({ subject: "", predicate: "", object: "", weight: "1" })
  const [editForm, setEditForm] = useState({
    title: "",
    category: "",
    question: "",
    answer: "",
    steps: "",
    search_terms: "",
    aliases: "",
    rlcraft_version: "",
    answer_type: "other",
    valid_status: "active",
    evidence: "",
  })

  const hits = useMemo(() => result?.hits || [], [result])
  const canEdit = hasPermission(user, "knowledge.edit")
  const canDelete = hasPermission(user, "knowledge.delete")
  const canQuestion = hasPermission(user, "knowledge.search")

  const handleSearch = async () => {
    const cleanQuery = query.trim()
    if (!cleanQuery) return
    if (cleanQuery.length > MAX_SEARCH_QUERY_LENGTH) {
      toast(`搜索内容过长，请控制在 ${MAX_SEARCH_QUERY_LENGTH} 字以内`, "error")
      return
    }
    setLoading(true)
    try {
      const data = await searchMemory(cleanQuery, limit, { mode })
      setResult(normalizePayload(data))
    } catch (error) {
      toast(errorMessage(error, "搜索失败"), "error")
    } finally {
      setLoading(false)
    }
  }

  const handleRandom = async () => {
    setLoading(true)
    try {
      const data = await randomSearchMemory(limit)
      setResult(normalizePayload(data))
      setQuery("")
    } catch (error) {
      toast(errorMessage(error, "随机抽取失败"), "error")
    } finally {
      setLoading(false)
    }
  }

  const openEditor = async (hit: SearchHit) => {
    if (isRelationHit(hit)) {
      setEditingRelationHit(hit)
      setRelationForm(relationFormFromHit(hit))
      return
    }
    const hash = hashShort(hit)
    const fullHash = hitHash(hit)
    if (!fullHash) {
      toast("这个结果没有可编辑的 hash", "error")
      return
    }
    setBusyHash(fullHash)
    try {
      const qa = extractQA(hit)
      const metadata = asRecord(hit.metadata)
      const details = extractDetails(hit)
      let source = {
        title: qa.title,
        category: asText(metadata.category),
        question: qa.question,
        answer: qa.answer || asText(hit.content),
        steps: details.steps,
        search_terms: details.search_terms,
        aliases: details.aliases,
        rlcraft_version: details.rlcraft_version,
        answer_type: details.answer_type,
        valid_status: details.valid_status,
        evidence: details.evidence,
      }
      try {
        const data = asRecord(await fetchSearchHitCard(fullHash))
        const card = asRecord(data.card)
        if (card.id != null) {
          source = {
            title: asText(card.title) || source.title,
            category: asText(card.category) || source.category,
            question: asText(card.question) || source.question,
            answer: asText(card.answer) || source.answer,
            steps: Array.isArray(card.steps) ? card.steps.map(asText).join("\n") : source.steps,
            search_terms: listToText(card.search_terms) || source.search_terms,
            aliases: listToText(card.aliases) || source.aliases,
            rlcraft_version: asText(card.rlcraft_version) || source.rlcraft_version,
            answer_type: asText(card.answer_type) || source.answer_type,
            valid_status: asText(card.valid_status) || source.valid_status,
            evidence: asText(card.evidence) || source.evidence,
          }
        }
      } catch {
        // 没有对应知识卡时，允许基于命中片段创建修订卡。
      }
      setEditingHit(hit)
      setEditForm({
        title: source.title,
        category: source.category,
        question: source.question,
        answer: source.answer,
        steps: source.steps,
        search_terms: source.search_terms,
        aliases: source.aliases,
        rlcraft_version: source.rlcraft_version,
        answer_type: source.answer_type || "other",
        valid_status: source.valid_status || "active",
        evidence: source.evidence,
      })
      if (!hash) toast("已打开编辑器", "info")
    } finally {
      setBusyHash("")
    }
  }

  const closeEditor = () => setEditingHit(null)

  const closeRelationEditor = () => {
    setEditingRelationHit(null)
    setRelationForm({ subject: "", predicate: "", object: "", weight: "1" })
  }

  const handleRelationChange = (key: keyof RelationEditForm, value: string) => {
    setRelationForm((prev) => ({ ...prev, [key]: value }))
  }

  const openQuestion = (hit: SearchHit) => {
    const fullHash = hitHash(hit)
    if (!fullHash) {
      toast("这个结果没有可提疑问的 hash", "error")
      return
    }
    setQuestionHit(hit)
    setQuestionText("")
  }

  const closeQuestion = () => {
    setQuestionHit(null)
    setQuestionText("")
  }

  const handleEditChange = (key: keyof typeof editForm, value: string) => {
    setEditForm((prev) => ({ ...prev, [key]: value }))
  }

  const saveEdit = async () => {
    if (!editingHit) return
    const fullHash = hitHash(editingHit)
    if (!fullHash || busyHash) return
    setBusyHash(fullHash)
    try {
      const payload = {
        ...editForm,
        steps: editForm.steps.split(/\r?\n/).map((item) => item.replace(/^\s*\d+[.、)]\s*/, "").trim()).filter(Boolean),
        search_terms: splitEditList(editForm.search_terms),
        aliases: splitEditList(editForm.aliases),
      }
      const data = asRecord(await updateSearchHit(fullHash, payload))
      toast(data.mode === "update" ? "已保存修改" : "已创建修订版，进入待审核", "success")
      closeEditor()
    } catch (error) {
      toast(errorMessage(error, "保存失败"), "error")
    } finally {
      setBusyHash("")
    }
  }

  const saveRelationEdit = async () => {
    if (!editingRelationHit || busyHash) return
    const fullHash = hitHash(editingRelationHit)
    const original = relationFormFromHit(editingRelationHit)
    const subject = relationForm.subject.trim()
    const predicate = relationForm.predicate.trim()
    const object = relationForm.object.trim()
    if (!subject || !predicate || !object) return
    const weight = Math.max(0.01, Math.min(1, Number(relationForm.weight) || 1))
    setBusyHash(fullHash || `${original.subject}:${original.predicate}:${original.object}`)
    try {
      await createGraphEdge(subject, predicate, object, weight)
      if (original.subject && original.predicate && original.object) {
        await deleteGraphEdge(original.subject, original.predicate, original.object, fullHash || undefined)
      }
      toast("图谱关系已更新", "success")
      closeRelationEditor()
      setResult((prev) => prev ? { ...prev, hits: (prev.hits || []).filter((item) => item !== editingRelationHit) } : prev)
    } catch (error) {
      toast(errorMessage(error, "保存图谱关系失败"), "error")
    } finally {
      setBusyHash("")
    }
  }

  const submitQuestion = async () => {
    if (!questionHit) return
    const fullHash = hitHash(questionHit)
    const doubt = questionText.trim()
    if (!fullHash || !doubt || busyHash) return
    const qa = extractQA(questionHit)
    const metadata = asRecord(questionHit.metadata)
    setBusyHash(fullHash)
    try {
      await questionSearchHit(fullHash, {
        doubt,
        title: qa.title,
        category: asText(metadata.category),
      })
      toast("已提交疑问，进入审核队列疑问分组", "success")
      closeQuestion()
    } catch (error) {
      toast(errorMessage(error, "提交疑问失败"), "error")
    } finally {
      setBusyHash("")
    }
  }

  const deleteHit = async (hit: SearchHit) => {
    const fullHash = paragraphHash(hit)
    if (!fullHash || busyHash) {
      if (!fullHash) toast("这个结果没有可删除的段落 hash", "error")
      return
    }
    if (!window.confirm("确定删除这条检索命中的知识吗？删除后会从检索段落中作废。")) return
    setBusyHash(fullHash)
    try {
      await deleteSearchHit(fullHash)
      setResult((prev) => prev ? { ...prev, hits: (prev.hits || []).filter((item) => hitHash(item) !== fullHash) } : prev)
      toast("已删除检索结果", "success")
    } catch (error) {
      toast(errorMessage(error, "删除失败"), "error")
    } finally {
      setBusyHash("")
    }
  }

  return (
    <>
      <Card
        title="知识检索"
        actions={
          <div className="inline-flex rounded-xl bg-default-100/60 p-0.5">
            {SEARCH_MODES.map((item) => (
              <button
                key={item.key}
                onClick={() => setMode(item.key)}
                className={`h-6.5 rounded-md px-2 text-xs font-medium transition-colors ${mode === item.key ? "bg-content1/45 text-default-900 shadow-sm" : "text-default-500 hover:text-default-900"}`}
              >
                {item.label}
              </button>
            ))}
          </div>
        }
      >
        <div className="mb-3 grid gap-2 sm:grid-cols-2 md:grid-cols-[minmax(0,1fr)_9rem_auto_auto]">
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-default-500" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSearch()}
            placeholder="输入游戏问题或关键词"
            className="h-9 w-full rounded-xl border border-white/10 bg-transparent pl-8 pr-3 text-sm text-default-900 placeholder:text-default-500 focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </div>
        <label className="relative">
          <SlidersHorizontal className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-default-500" />
          <select
            className={`${TOOL_INPUT} h-9 w-full appearance-none pl-8`}
            value={limit}
            onChange={(event) => setLimit(Number(event.target.value))}
          >
            {[8, 12, 20, 50].map((item) => <option key={item} value={item}>返回 {item}</option>)}
          </select>
        </label>
        <Button className="w-full md:w-auto" onClick={handleSearch} disabled={loading || !query.trim()}>
          <Search className="h-4 w-4" />{loading ? "检索中" : "搜索"}
        </Button>
        <Button className="w-full md:w-auto" variant="secondary" onClick={handleRandom} disabled={loading}>
          <Shuffle className="h-4 w-4" />随机来一轮
        </Button>
      </div>

        {loading && <Loading className="mt-4" />}

        {result && !loading && (
          <div className="space-y-3">
          {result.error && (
            <div className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {result.error}
            </div>
          )}
          {result.filtered && (
            <div className="rounded-md border border-warning/30 bg-warning/10 px-3 py-2 text-sm text-warning-foreground">
              当前检索被来源过滤规则拦截
            </div>
          )}
          <div className="flex min-w-0 flex-wrap items-center gap-2 text-xs text-default-500">
            <span className="inline-flex items-center gap-1 rounded-md bg-default-100/60 px-2 py-1 text-default-900">
              <Database className="h-3 w-3" />命中 {hits.length}
            </span>
            {result.count != null && result.count !== hits.length && <span>总数 {result.count}</span>}
            {result.summary && <span className="min-w-full flex-1 truncate sm:min-w-0">{result.summary.replace(/\s+/g, " ")}</span>}
          </div>

          {hits.length === 0 ? (
            <p className="text-sm text-default-500">没有找到匹配的知识。</p>
          ) : (
            <div className="space-y-2">
              {hits.map((hit, index) => {
                const qa = extractQA(hit)
                const score = displayScore(hit)
                const meta = metaLine(hit)
                const shortHash = hashShort(hit)
                const fullHash = hitHash(hit)
                const busy = Boolean(fullHash && busyHash === fullHash)
                const timeText = eventTime(hit)
                const content = asText(hit.content)
                const edits = editCount(hit)
                const metadata = asRecord(hit.metadata)
                const relationHit = isRelationHit(hit)
                return (
                  <div key={`${shortHash || index}-${index}`} className={relationHit ? RELATION_RESULT_BORDER : RESULT_BORDER}>
                    <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span className="inline-flex h-5 min-w-5 items-center justify-center rounded-md bg-primary/15 px-1.5 text-[0.65rem] font-semibold text-primary">
                          #{index + 1}
                        </span>
                        <span className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[0.65rem] font-semibold ${relationHit ? "border border-sky-400/40 bg-sky-500/15 text-sky-700 dark:text-sky-200" : "bg-default-100/60 text-default-500"}`}>
                          {relationHit ? <GitBranch className="h-3 w-3" /> : <Layers3 className="h-3 w-3" />}{resultTypeLabel(hit)}
                        </span>
                        {relationHit && (
                          <span className="rounded-md border border-sky-400/35 bg-sky-500/10 px-1.5 py-0.5 text-[0.65rem] font-semibold text-sky-700 dark:text-sky-200">
                            图谱结果，仅作关系参考
                          </span>
                        )}
                        <span className="rounded-md border border-white/10 bg-default-100/60 px-1.5 py-0.5 text-[0.65rem] font-semibold text-default-500">
                          编辑 {edits} 次
                        </span>
                        <span className="rounded-md border border-white/10 bg-default-100/60 px-1.5 py-0.5 text-[0.65rem] font-semibold text-default-500">
                          {answerTypeLabel(metadata.answer_type)}
                        </span>
                        <span className="rounded-md border border-white/10 bg-default-100/60 px-1.5 py-0.5 text-[0.65rem] font-semibold text-default-500">
                          {validStatusLabel(metadata.valid_status)}
                        </span>
                        {asText(metadata.rlcraft_version).trim() && (
                          <span className="rounded-md border border-warning/25 bg-warning/10 px-1.5 py-0.5 text-[0.65rem] font-semibold text-warning-foreground">
                            版本 {asText(metadata.rlcraft_version).trim()}
                          </span>
                        )}
                        {score.rank && (
                          <span className="rounded-md bg-success/15 px-1.5 py-0.5 text-[0.65rem] font-semibold text-success">
                            rank {score.rank}{score.raw && score.raw !== score.rank ? ` · raw ${score.raw}` : ""}
                          </span>
                        )}
                      </div>
                      <div className="flex flex-wrap items-center gap-2 text-[0.7rem] text-default-500">
                        {timeText && <span>{timeText}</span>}
                        {shortHash && <span className="inline-flex items-center gap-1"><Hash className="h-3 w-3" />{shortHash}</span>}
                      </div>
                    </div>

                    <div className="space-y-2">
                      <div>
                        <div className="mb-1 flex flex-wrap items-center gap-2">
                          <BookOpen className="h-3.5 w-3.5 text-primary" />
                          <h3 className="text-sm font-semibold leading-snug text-default-900">{qa.title}</h3>
                        </div>
                        {meta.length > 0 && (
                          <p className="text-[0.72rem] text-default-500">{meta.join(" · ")}</p>
                        )}
                      </div>

                      {qa.question && (
                        <div className="rounded-md border border-white/10 bg-content1/45 px-2.5 py-2">
                          <div className="mb-1 text-[0.65rem] font-semibold text-primary">Q</div>
                          <p className="whitespace-pre-wrap text-sm leading-relaxed">{qa.question}</p>
                        </div>
                      )}

                      {qa.answer && (
                        <div className="rounded-md border border-white/10 bg-content1/50 px-2.5 py-2">
                          <div className="mb-1 text-[0.65rem] font-semibold text-success">A</div>
                          <p className="whitespace-pre-wrap text-sm leading-relaxed">{truncate(qa.answer, 900)}</p>
                        </div>
                      )}

                      {!qa.answer && content && (
                        <p className="whitespace-pre-wrap text-sm leading-relaxed">{truncate(content, 900)}</p>
                      )}

                      {content && (qa.question || qa.answer) && (
                        <details className="text-xs text-default-500">
                          <summary className="cursor-pointer select-none hover:text-default-900">原始片段</summary>
                          <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap rounded-md bg-default-100/40 p-2 font-mono text-[0.7rem] leading-relaxed">
                            {content}
                          </pre>
                        </details>
                      )}

                      <div className="flex flex-wrap gap-1.5 pt-1">
                        {canQuestion && (
                          <Button variant="outline" size="sm" disabled={busy || !fullHash} onClick={() => openQuestion(hit)}>
                            <CircleHelp className="h-3 w-3" />疑问
                          </Button>
                        )}
                        {canEdit && (
                          <Button variant="outline" size="sm" disabled={busy || !fullHash} onClick={() => openEditor(hit)}>
                            <Pencil className="h-3 w-3" />编辑
                          </Button>
                        )}
                        {canDelete && (
                          <Button variant="ghost" size="sm" disabled={busy || !fullHash} onClick={() => deleteHit(hit)}>
                            <Trash2 className="h-3 w-3" />删除
                          </Button>
                        )}
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
          </div>
        )}
      </Card>
      {editingHit && (
        <SearchEditor
          hit={editingHit}
          editForm={editForm}
          busy={Boolean(busyHash)}
          onChange={handleEditChange}
          onClose={closeEditor}
          onSave={saveEdit}
        />
      )}
      {editingRelationHit && (
        <RelationEditor
          hit={editingRelationHit}
          form={relationForm}
          busy={Boolean(busyHash)}
          onChange={handleRelationChange}
          onClose={closeRelationEditor}
          onSave={saveRelationEdit}
        />
      )}
      {questionHit && (
        <QuestionDialog
          hit={questionHit}
          value={questionText}
          busy={Boolean(busyHash)}
          onChange={setQuestionText}
          onClose={closeQuestion}
          onSubmit={submitQuestion}
        />
      )}
    </>
  )
}
