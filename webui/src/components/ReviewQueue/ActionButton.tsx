import { useState } from "react"
import Button from "@/components/Button"
import type { ActionKey } from "./types"
import { ACTION_MATRIX, SELF_REVIEW_TOOLTIP } from "./constants"

interface ActionButtonProps {
  status: string
  action: ActionKey
  onClick: () => void
  busy?: boolean
  disabledByPermission?: boolean
  isOwnEdit?: boolean
  size?: "sm" | "default"
  className?: string
  icon?: React.ReactNode
  labelOverride?: string
  tooltipOverride?: string
  variantOverride?: "primary" | "secondary" | "outline" | "ghost" | "destructive" | "success"
}

// 渲染单个动作按钮，自动读取 ACTION_MATRIX 拿到“真实后果”tooltip。
// 当无权限或自审锁触发时，tooltip 会替换为对应原因。
export default function ActionButton({
  status,
  action,
  onClick,
  busy,
  disabledByPermission,
  isOwnEdit,
  size = "sm",
  className,
  icon,
  labelOverride,
  tooltipOverride,
  variantOverride,
}: ActionButtonProps) {
  const [showTip, setShowTip] = useState(false)
  const spec = ACTION_MATRIX[status]?.[action]
  if (!spec) return null
  const selfLocked = (action === "approve" || action === "reject") && Boolean(isOwnEdit)
  const disabled = Boolean(busy || disabledByPermission || selfLocked)
  const label = labelOverride ?? spec.label
  let tooltip = tooltipOverride ?? spec.tooltip
  if (disabledByPermission) tooltip = "无对应权限"
  else if (selfLocked) tooltip = SELF_REVIEW_TOOLTIP
  else if (busy) tooltip = "正在处理…"
  const variant = variantOverride ?? spec.variant
  return (
    <span className="relative inline-flex">
      <Button
        variant={variant}
        size={size}
        onClick={onClick}
        disabled={disabled}
        className={className}
        aria-label={tooltip}
        onMouseEnter={() => setShowTip(true)}
        onMouseLeave={() => setShowTip(false)}
        onFocus={() => setShowTip(true)}
        onBlur={() => setShowTip(false)}
      >
        {icon}
        {busy ? "处理中" : label}
      </Button>
      {showTip && (
        <span className="pointer-events-none absolute bottom-full left-1/2 z-50 mb-1.5 w-max max-w-xs -translate-x-1/2 rounded-md border border-black/10 bg-gray-900 px-2 py-1.5 text-[0.7rem] leading-relaxed text-white shadow-lg dark:border-white/10 dark:bg-gray-800">
          {tooltip}
        </span>
      )}
    </span>
  )
}
