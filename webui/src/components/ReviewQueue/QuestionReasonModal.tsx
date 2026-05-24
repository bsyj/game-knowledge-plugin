import { useEffect } from "react"
import { createPortal } from "react-dom"
import { CircleHelp, X } from "lucide-react"
import Button from "@/components/Button"
import type { CardItem } from "./types"
import { EDIT_INPUT_CLASS } from "./constants"

interface Props {
  card: CardItem
  value: string
  busy: boolean
  onChange: (value: string) => void
  onClose: () => void
  onSubmit: () => void
}

function truncate(value: string | undefined, max: number): string {
  const text = String(value || "").trim()
  return text.length > max ? `${text.slice(0, max - 1)}...` : text
}

export default function QuestionReasonModal({ card, value, busy, onChange, onClose, onSubmit }: Props) {
  useEffect(() => {
    function handler(event: KeyboardEvent) {
      if (event.isComposing) return
      if (event.key === "Escape") {
        event.preventDefault()
        onClose()
      } else if ((event.ctrlKey || event.metaKey) && event.key === "Enter" && !busy) {
        event.preventDefault()
        onSubmit()
      }
    }
    window.addEventListener("keydown", handler)
    return () => window.removeEventListener("keydown", handler)
  }, [busy, onClose, onSubmit])

  return createPortal(
    <div className="gk-modal-overlay fixed inset-0 z-[9999] flex items-center justify-center p-3 md:p-6">
      <div className="gk-modal-panel w-full max-w-2xl overflow-hidden rounded-2xl">
        <div className="gk-modal-header flex items-start justify-between gap-3 border-b px-4 py-3">
          <div>
            <h3 className="text-sm font-semibold">标记为疑问 #{card.id}</h3>
            <p className="mt-0.5 text-xs text-default-500">
              只会改为「疑问」状态，不会写入检索库
              <span className="ml-2 text-default-400">(Ctrl/⌘+Enter 提交，Esc 关闭)</span>
            </p>
          </div>
          <Button variant="ghost" size="sm" onClick={onClose} title="关闭 (Esc)">
            <X className="h-3 w-3" />
          </Button>
        </div>

        <div className="space-y-3 px-4 py-3">
          <div className="gk-modal-surface rounded-lg p-2.5">
            <div className="text-xs font-semibold text-default-900">{card.title || "未命名知识"}</div>
            {card.question && <p className="mt-1 text-xs text-default-500">Q: {truncate(card.question, 180)}</p>}
            {card.answer && <p className="mt-1 text-xs text-default-500">A: {truncate(card.answer, 260)}</p>}
          </div>
          <label className="grid gap-1 text-xs text-default-500">
            疑问理由（可留空）
            <textarea
              className={`${EDIT_INPUT_CLASS} min-h-32 resize-y`}
              value={value}
              onChange={(event) => onChange(event.target.value)}
              placeholder="建议补一句哪里不对、哪里缺答案，方便其他审核员接手"
              autoFocus
            />
          </label>
          <p className="text-xs text-default-400">置为「疑问」后会进入疑问 Tab，卡片内容保持可继续编辑。</p>
        </div>

        <div className="gk-modal-footer flex justify-end gap-2 border-t px-4 py-3">
          <Button variant="outline" size="sm" onClick={onClose} title="放弃并关闭 (Esc)">取消</Button>
          <Button variant="primary" size="sm" onClick={onSubmit} disabled={busy} title="提交 (Ctrl/⌘ + Enter)">
            <CircleHelp className="h-3 w-3" />提交疑问
          </Button>
        </div>
      </div>
    </div>,
    document.body,
  )
}
