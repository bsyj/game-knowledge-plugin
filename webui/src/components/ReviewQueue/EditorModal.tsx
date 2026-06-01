import { useEffect } from "react"
import { createPortal } from "react-dom"
import { Save, X } from "lucide-react"
import Button from "@/components/Button"
import type { CardItem, EditForm } from "./types"
import { ANSWER_TYPE_OPTIONS, CATEGORY_OPTIONS, EDIT_INPUT_CLASS, VALID_STATUS_OPTIONS } from "./constants"

interface Props {
  card: CardItem
  form: EditForm
  busy: boolean
  onChange: (key: keyof EditForm, value: string) => void
  onClose: () => void
  onSave: () => void
}

export default function EditorModal({ card, form, busy, onChange, onClose, onSave }: Props) {
  // Esc 关闭 + Ctrl/⌘ + Enter 保存
  useEffect(() => {
    function handler(event: KeyboardEvent) {
      if (event.isComposing) return
      if (event.key === "Escape") {
        event.preventDefault()
        onClose()
      } else if ((event.ctrlKey || event.metaKey) && event.key === "Enter" && !busy) {
        event.preventDefault()
        onSave()
      }
    }
    window.addEventListener("keydown", handler)
    return () => window.removeEventListener("keydown", handler)
  }, [busy, onClose, onSave])

  return createPortal(
    <div className="gk-modal-overlay fixed inset-0 z-[9999] flex items-center justify-center p-3 md:p-6">
      <div className="gk-modal-panel flex max-h-[calc(100dvh-2rem)] w-full max-w-3xl flex-col overflow-hidden rounded-2xl md:max-h-[calc(100dvh-3rem)]">
        <div className="gk-modal-header flex shrink-0 items-start justify-between gap-3 border-b px-4 py-3">
          <div>
            <h3 className="text-sm font-semibold">编辑知识卡片 #{card.id}</h3>
            <p className="mt-0.5 text-xs text-default-500">
              {card.review_status === "approved"
                ? "已通过卡片：保存将创建修订版并回到待审核"
                : card.review_status === "needs_answer"
                  ? "疑问卡：补完 A 字段后会重新进入审核流程"
                  : "未通过卡片：保存将原地更新内容"}
              <span className="ml-2 text-default-400">(Ctrl/⌘+Enter 保存，Esc 关闭)</span>
            </p>
          </div>
          <Button variant="ghost" size="sm" onClick={onClose} title="关闭 (Esc)"><X className="h-3 w-3" /></Button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
          <div className="grid gap-3">
            <label className="grid gap-1 text-xs text-default-500">
              标题
              <input className={EDIT_INPUT_CLASS} value={form.title} onChange={(event) => onChange("title", event.target.value)} />
            </label>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="grid gap-1 text-xs text-default-500">
                分类
                <select className={EDIT_INPUT_CLASS} value={form.category} onChange={(event) => onChange("category", event.target.value)}>
                  <option value="">未分类</option>
                  {CATEGORY_OPTIONS.map((item) => <option key={item} value={item}>{item}</option>)}
                </select>
              </label>
              <label className="grid gap-1 text-xs text-default-500">
                游戏版本
                <input className={EDIT_INPUT_CLASS} value={form.rlcraft_version} onChange={(event) => onChange("rlcraft_version", event.target.value)} placeholder="例如 2.9 / 3.3 / 当前服版本" />
              </label>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="grid gap-1 text-xs text-default-500">
                答案类型
                <select className={EDIT_INPUT_CLASS} value={form.answer_type} onChange={(event) => onChange("answer_type", event.target.value)}>
                  {ANSWER_TYPE_OPTIONS.map((item) => <option key={item.key} value={item.key}>{item.label}</option>)}
                </select>
              </label>
              <label className="grid gap-1 text-xs text-default-500">
                有效状态
                <select className={EDIT_INPUT_CLASS} value={form.valid_status} onChange={(event) => onChange("valid_status", event.target.value)}>
                  {VALID_STATUS_OPTIONS.map((item) => <option key={item.key} value={item.key}>{item.label}</option>)}
                </select>
              </label>
            </div>
            <label className="grid gap-1 text-xs text-default-500">
              Q
              <textarea className={`${EDIT_INPUT_CLASS} min-h-24 resize-y`} value={form.question} onChange={(event) => onChange("question", event.target.value)} />
            </label>
            <label className="grid gap-1 text-xs text-default-500">
              A
              <textarea className={`${EDIT_INPUT_CLASS} min-h-36 resize-y`} value={form.answer} onChange={(event) => onChange("answer", event.target.value)} />
            </label>
            <label className="grid gap-1 text-xs text-default-500">
              检索关键词（逗号/换行分隔）
              <textarea className={`${EDIT_INPUT_CLASS} min-h-20 resize-y`} value={form.search_terms} onChange={(event) => onChange("search_terms", event.target.value)} placeholder="物品、附魔、boss、报错原文、配置项、群内简称" />
            </label>
            <label className="grid gap-1 text-xs text-default-500">
              别名
              <input className={EDIT_INPUT_CLASS} value={form.aliases} onChange={(event) => onChange("aliases", event.target.value)} placeholder="游戏名、简称、俗称等" />
            </label>
            <label className="grid gap-1 text-xs text-default-500">
              证据/来源说明
              <textarea className={`${EDIT_INPUT_CLASS} min-h-20 resize-y`} value={form.evidence} onChange={(event) => onChange("evidence", event.target.value)} />
            </label>
          </div>
        </div>
        <div className="gk-modal-footer flex shrink-0 justify-end gap-2 border-t px-4 py-3">
          <Button variant="outline" size="sm" onClick={onClose} title="放弃修改并关闭 (Esc)">取消</Button>
          <Button variant="primary" size="sm" onClick={onSave} disabled={busy} title="保存 (Ctrl/⌘ + Enter)">
            <Save className="h-3 w-3" />保存
          </Button>
        </div>
      </div>
    </div>,
    document.body,
  )
}
