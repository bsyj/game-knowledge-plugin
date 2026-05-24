import { useEffect, useState, useCallback } from "react"
import { RefreshCw, Archive, Trash2 } from "lucide-react"
import { fetchRecycleBin, v5Action } from "@/lib/api"
import { useToast } from "@/components/Toast"
import Card from "@/components/Card"
import Button from "@/components/Button"
import Loading from "@/components/Loading"
import { formatDate, truncate } from "@/lib/utils"

interface DeletedItem {
  id: string
  doc_id?: string
  content?: string
  deleted_at?: number | string
  source?: string
}

export default function MaintenancePanel() {
  const { toast } = useToast()
  const [bin, setBin] = useState<DeletedItem[]>([])
  const [loading, setLoading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = (await fetchRecycleBin()) as { items?: DeletedItem[]; deleted?: DeletedItem[] }
      setBin((data.items || data.deleted || []) as DeletedItem[])
    } catch { toast("加载回收站失败", "error") } finally { setLoading(false) }
  }, [toast])

  useEffect(() => { load() }, [load])

  const handleAction = async (action: string, id: string) => {
    try { await v5Action(action, { id }); toast("操作成功", "success"); load() } catch { toast("操作失败", "error") }
  }

  return (
    <div className="space-y-5">
      <Card title="维护操作">
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={async () => { try { await v5Action("cleanup"); toast("清理完成", "success"); load() } catch { toast("操作失败", "error") } }}><Archive className="h-4 w-4" />清理过期数据</Button>
          <Button variant="outline" onClick={async () => { try { await v5Action("compact"); toast("压缩完成", "success") } catch { toast("操作失败", "error") } }}><Archive className="h-4 w-4" />压缩数据库</Button>
          <Button variant="destructive" onClick={async () => { try { await v5Action("purge"); toast("清空完成", "success"); load() } catch { toast("操作失败", "error") } }}><Trash2 className="h-4 w-4" />清空回收站</Button>
        </div>
      </Card>

      <Card title="回收站" actions={<Button variant="outline" size="sm" onClick={load}><RefreshCw className="h-3 w-3" />刷新</Button>}>
        {loading ? <Loading />
        : bin.length === 0 ? <p className="text-sm text-default-500">回收站为空</p>
        : (
          <div className="space-y-2">
            {bin.map((item) => (
              <div key={item.id} className="rounded-xl border border-white/10 bg-content1/45 p-3">
                <div className="mb-1 flex items-center justify-between">
                  <code className="text-xs text-default-500">{item.doc_id || item.id}</code>
                  <span className="text-[0.7rem] text-default-500">{formatDate(item.deleted_at)}</span>
                </div>
                <p className="text-sm">{truncate(item.content || "", 300)}</p>
                <div className="mt-2 flex gap-1.5">
                  <Button variant="success" size="sm" onClick={() => handleAction("restore", item.id)}><Archive className="h-3 w-3" />恢复</Button>
                  <Button variant="destructive" size="sm" onClick={() => handleAction("permanent-delete", item.id)}><Trash2 className="h-3 w-3" />永久删除</Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  )
}