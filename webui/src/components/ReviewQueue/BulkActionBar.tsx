import { Check, Loader2, Trash2, X } from "lucide-react"
import Button from "@/components/Button"
import type { AuthUser } from "@/lib/api"
import { hasPermission } from "@/lib/api"
import type { ActionKey, BulkProgress } from "./types"

interface Props {
  user: AuthUser
  selectionCount: number
  progress: BulkProgress
  onRun: (action: ActionKey) => void
  onClear: () => void
}

const ACTION_DESCRIPTIONS: Record<ActionKey, string> = {
  approve: "对所有选中卡片执行【通过】：写入检索库（受到后端 3 并发池保护，前端串行调度）",
  reject: "对所有选中卡片执行【拒绝】：不写入检索库，可在【已拒绝】Tab 找回",
  delete: "对所有选中卡片执行【删除】：未通过卡片永久删除；已通过卡片会先从检索库移除再标记为已拒绝",
  edit: "",
  question: "对选中卡片标记疑问，等待补充答案后再进入审核流程",
}

export default function BulkActionBar({ user, selectionCount, progress, onRun, onClear }: Props) {
  if (selectionCount === 0 && !progress.running) return null
  const canApprove = hasPermission(user, "review.approve")
  const canReject = hasPermission(user, "review.reject")
  const canDelete = hasPermission(user, "knowledge.delete")
  const running = progress.running
  const percent = progress.total > 0 ? Math.round((progress.done / progress.total) * 100) : 0

  return (
    <div className="sticky bottom-0 z-10 mt-2 flex flex-col gap-2 rounded-xl border border-primary/30 bg-primary/8 px-3 py-2 backdrop-blur-md">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="inline-flex h-6 items-center rounded-md bg-primary/15 px-2 font-semibold text-primary">
          {running ? `批量${progress.action === "approve" ? "通过" : progress.action === "reject" ? "拒绝" : "删除"}中… ${progress.done}/${progress.total}` : `已选 ${selectionCount} 张`}
        </span>
        {!running && (
          <>
            <Button
              variant="success"
              size="sm"
              onClick={() => onRun("approve")}
              disabled={!canApprove}
              title={canApprove ? ACTION_DESCRIPTIONS.approve : "无对应权限"}
            >
              <Check className="h-3 w-3" />
              批量通过 ({selectionCount})
            </Button>
            <Button
              variant="destructive"
              size="sm"
              onClick={() => onRun("reject")}
              disabled={!canReject}
              title={canReject ? ACTION_DESCRIPTIONS.reject : "无对应权限"}
            >
              <X className="h-3 w-3" />
              批量拒绝 ({selectionCount})
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => onRun("delete")}
              disabled={!canDelete}
              title={canDelete ? ACTION_DESCRIPTIONS.delete : "无对应权限"}
            >
              <Trash2 className="h-3 w-3" />
              批量删除 ({selectionCount})
            </Button>
            <Button variant="ghost" size="sm" onClick={onClear} title="清空选中（也可按 Esc）">
              清空选择
            </Button>
          </>
        )}
        {running && (
          <span className="inline-flex items-center gap-1 text-[0.7rem] text-default-600">
            <Loader2 className="h-3 w-3 animate-spin" />
            处理中
          </span>
        )}
      </div>
      {(running || progress.total > 0) && (
        <div className="h-1 overflow-hidden rounded-full bg-default-100/60">
          <div
            className="h-full rounded-full bg-primary transition-all"
            style={{ width: `${Math.min(100, percent)}%` }}
          />
        </div>
      )}
      {progress.failed.length > 0 && !running && (
        <div className="rounded-md border border-destructive/25 bg-destructive/5 px-2 py-1.5 text-[0.7rem] text-destructive">
          有 {progress.failed.length} 张失败：
          {progress.failed.slice(0, 4).map((item) => `#${item.id} (${item.reason})`).join("、")}
          {progress.failed.length > 4 ? "…" : ""}
        </div>
      )}
    </div>
  )
}
