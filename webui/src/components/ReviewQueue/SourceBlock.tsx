import { useState } from "react"
import { Copy, Filter, Hash, Users } from "lucide-react"
import type { CardItem } from "./types"
import { useToast } from "@/components/Toast"

interface Props {
  card: CardItem
  onFilterByGroup: (groupId: string, groupName: string) => void
}

// 显示来源群名/群 ID/stream，提供复制和“筛选此源”快捷
export default function SourceBlock({ card, onFilterByGroup }: Props) {
  const { toast } = useToast()
  const [copied, setCopied] = useState<string | null>(null)
  const groupId = String(card.source_group_id || "").trim()
  const groupName = String(card.source_group_name || "").trim()
  const streamId = String(card.source_stream_id || "").trim()
  const platform = String(card.platform || card.source_platform || "").trim()
  if (!groupId && !groupName && !streamId && !platform) return null

  const copy = async (value: string, kind: string) => {
    try {
      await navigator.clipboard.writeText(value)
      setCopied(value)
      toast(`已复制${kind}`, "success")
      window.setTimeout(() => setCopied((current) => (current === value ? null : current)), 1200)
    } catch {
      toast("复制失败", "error")
    }
  }

  return (
    <div className="rounded-lg border border-white/10 bg-default-100/30 p-3 text-xs">
      <div className="mb-2 flex items-center gap-2">
        <span className="text-[0.65rem] font-semibold text-default-600">来源</span>
        {platform && <span className="rounded-md bg-default-100/60 px-1.5 py-0.5 text-[0.62rem] text-default-500">{platform}</span>}
      </div>
      <div className="grid gap-1.5">
        {(groupName || groupId) && (
          <div className="flex flex-wrap items-center gap-1.5">
            <Users className="h-3 w-3 shrink-0 text-default-500" />
            <span className="text-default-700">{groupName || "未命名群"}</span>
            {groupId && (
              <span className="font-mono text-[0.65rem] text-default-500">#{groupId}</span>
            )}
            {groupId && (
              <button
                type="button"
                onClick={() => copy(groupId, "群 ID")}
                className="ml-auto inline-flex h-5 items-center gap-0.5 rounded-md border border-white/10 bg-content1/40 px-1.5 text-[0.62rem] text-default-500 hover:text-default-900"
                title="复制群 ID"
              >
                <Copy className="h-2.5 w-2.5" />
                {copied === groupId ? "已复制" : "复制 ID"}
              </button>
            )}
            {groupId && (
              <button
                type="button"
                onClick={() => onFilterByGroup(groupId, groupName)}
                className="inline-flex h-5 items-center gap-0.5 rounded-md border border-primary/25 bg-primary/10 px-1.5 text-[0.62rem] font-semibold text-primary hover:bg-primary/15"
                title="把列表过滤到此群"
              >
                <Filter className="h-2.5 w-2.5" />
                筛选此源
              </button>
            )}
          </div>
        )}
        {streamId && (
          <div className="flex flex-wrap items-center gap-1.5">
            <Hash className="h-3 w-3 shrink-0 text-default-500" />
            <span className="font-mono text-[0.7rem] text-default-700">{streamId}</span>
            <button
              type="button"
              onClick={() => copy(streamId, "Stream ID")}
              className="ml-auto inline-flex h-5 items-center gap-0.5 rounded-md border border-white/10 bg-content1/40 px-1.5 text-[0.62rem] text-default-500 hover:text-default-900"
              title="复制 Stream ID"
            >
              <Copy className="h-2.5 w-2.5" />
              {copied === streamId ? "已复制" : "复制"}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
