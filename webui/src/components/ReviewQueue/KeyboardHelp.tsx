import { createPortal } from "react-dom"
import { X } from "lucide-react"
import Button from "@/components/Button"
import { KEYBOARD_SHORTCUTS } from "./constants"

interface Props {
  open: boolean
  onClose: () => void
}

export default function KeyboardHelp({ open, onClose }: Props) {
  if (!open) return null
  return createPortal(
    <div className="gk-modal-overlay fixed inset-0 z-[9999] flex items-center justify-center p-3 md:p-6" onClick={onClose}>
      <div
        className="gk-modal-panel flex w-full max-w-lg flex-col overflow-hidden rounded-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="gk-modal-header flex items-center justify-between gap-3 border-b px-4 py-3">
          <h3 className="text-sm font-semibold">键盘快捷键</h3>
          <Button variant="ghost" size="sm" onClick={onClose} title="关闭 (Esc)"><X className="h-3 w-3" /></Button>
        </div>
        <div className="max-h-[60dvh] overflow-y-auto px-4 py-3">
          <ul className="grid gap-1.5">
            {KEYBOARD_SHORTCUTS.map((item) => (
              <li key={item.keys} className="gk-modal-surface flex items-center justify-between gap-3 rounded-md px-3 py-1.5 text-xs">
                <span className="text-default-700">{item.label}</span>
                <kbd className="rounded-md border border-[var(--gk-input-border)] bg-default-100/60 px-1.5 py-0.5 font-mono text-[0.7rem] text-default-800">
                  {item.keys}
                </kbd>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-[0.7rem] text-default-500">提示：聚焦在输入框/编辑器内时，单字母快捷键不会触发。中文输入法激活时也会被跳过。</p>
        </div>
      </div>
    </div>,
    document.body,
  )
}
