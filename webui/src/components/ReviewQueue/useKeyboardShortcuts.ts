import { useEffect } from "react"

export interface ShortcutHandlers {
  onNext: () => void
  onPrev: () => void
  onApprove: () => void
  onReject: () => void
  onDelete: () => void
  onEdit: () => void
  onToggleBulk: () => void
  onToggleSelectCurrent: () => void
  onFocusSearch: () => void
  onEscape: () => void
  onShowHelp: () => void
  enabled: boolean
}

function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  if (target.isContentEditable) return true
  const tag = target.tagName
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT"
}

export default function useKeyboardShortcuts(handlers: ShortcutHandlers) {
  useEffect(() => {
    if (!handlers.enabled) return
    function onKeyDown(event: KeyboardEvent) {
      if (event.isComposing) return
      const typing = isTypingTarget(event.target)
      // "/" 在非编辑区聚焦搜索
      if (event.key === "/" && !typing) {
        event.preventDefault()
        handlers.onFocusSearch()
        return
      }
      // Esc 全场景响应
      if (event.key === "Escape") {
        handlers.onEscape()
        return
      }
      // 编辑区内不响应字母快捷键
      if (typing) return
      if (event.metaKey || event.ctrlKey || event.altKey) return
      switch (event.key) {
        case "j":
        case "ArrowDown":
          event.preventDefault()
          handlers.onNext()
          break
        case "k":
        case "ArrowUp":
          event.preventDefault()
          handlers.onPrev()
          break
        case " ":
          event.preventDefault()
          handlers.onToggleSelectCurrent()
          break
        case "a":
          event.preventDefault()
          handlers.onApprove()
          break
        case "r":
          event.preventDefault()
          handlers.onReject()
          break
        case "e":
          event.preventDefault()
          handlers.onEdit()
          break
        case "d":
          event.preventDefault()
          handlers.onDelete()
          break
        case "x":
          event.preventDefault()
          handlers.onToggleBulk()
          break
        case "?":
          event.preventDefault()
          handlers.onShowHelp()
          break
        default:
          break
      }
    }
    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
  }, [handlers])
}
