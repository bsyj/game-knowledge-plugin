import { useEffect, useState, useCallback } from "react"
import { Trash2, RefreshCw } from "lucide-react"
import { fetchSources, deleteSource } from "@/lib/api"
import { useToast } from "@/components/Toast"
import Card from "@/components/Card"
import Button from "@/components/Button"
import Loading from "@/components/Loading"

interface Source {
  source: string
  count?: number
  last_used?: number | string
  docs?: number
}

export default function SourcesPanel() {
  const { toast } = useToast()
  const [sources, setSources] = useState<Source[]>([])
  const [loading, setLoading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = (await fetchSources()) as { sources?: Source[]; items?: Source[] }
      setSources((data.sources || data.items || []) as Source[])
    } catch { toast("加载来源失败", "error") } finally { setLoading(false) }
  }, [toast])

  useEffect(() => { load() }, [load])

  const handleDelete = async (source: string) => {
    if (!window.confirm(`确定删除来源「${source}」吗？相关记忆会被移入删除流程。`)) return
    try { await deleteSource(source); toast("来源已删除", "success"); load() } catch { toast("删除失败", "error") }
  }

  return (
    <Card title="记忆来源" actions={<Button variant="outline" size="sm" onClick={load}><RefreshCw className="h-3 w-3" />刷新</Button>}>
      {loading ? <Loading />
      : sources.length === 0 ? <p className="text-sm text-default-500">暂无来源</p>
      : (
        <div className="overflow-x-auto overscroll-x-contain rounded-xl border border-white/10">
          <table className="min-w-[28rem] w-full border-collapse text-xs">
            <thead>
              <tr>
                <th className="h-10 px-4 text-left font-medium text-default-500 border-b border-white/10">来源</th>
                <th className="h-10 px-4 text-left font-medium text-default-500 border-b border-white/10">文档数</th>
                <th className="h-10 px-4 text-right font-medium text-default-500 border-b border-white/10">操作</th>
              </tr>
            </thead>
            <tbody>
              {sources.map((s) => (
                <tr key={s.source} className="transition-colors hover:bg-default-100/65 dark:hover:bg-white/5">
                  <td className="px-4 py-2.5 border-b border-white/10 font-medium break-all">{s.source}</td>
                  <td className="px-4 py-2.5 border-b border-white/10 text-default-500">{s.docs ?? s.count ?? "-"}</td>
                  <td className="px-4 py-2.5 border-b border-white/10 text-right">
                    <Button variant="ghost" size="sm" onClick={() => handleDelete(s.source)}><Trash2 className="h-3 w-3" /></Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}
