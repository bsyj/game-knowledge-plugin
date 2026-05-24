import { useEffect, useState, useCallback } from "react"
import { RefreshCw, Save, CheckCircle, AlertTriangle, Database } from "lucide-react"
import { fetchRuntimeConfig, runtimeSave, runtimeSelfCheck, runtimeRefreshSelfCheck, runtimeAutoSave, rebuildVectors } from "@/lib/api"
import { useToast } from "@/components/Toast"
import Card from "@/components/Card"
import Button from "@/components/Button"
import Loading from "@/components/Loading"

export default function RuntimePanel() {
  const { toast } = useToast()
  const [config, setConfig] = useState<Record<string, unknown> | null>(null)
  const [check, setCheck] = useState<unknown>(null)
  const [loading, setLoading] = useState(false)
  const [autoSave, setAutoSave] = useState(false)
  const [autoInterval, setAutoInterval] = useState(300)

  const loadConfig = useCallback(async () => {
    setLoading(true)
    try {
      const data = await fetchRuntimeConfig()
      setConfig(data as Record<string, unknown>)
      const c = data as Record<string, unknown>
      if (typeof c?.auto_save === "boolean") setAutoSave(c.auto_save)
      if (typeof c?.auto_save_interval === "number") setAutoInterval(c.auto_save_interval)
    } catch { toast("加载配置失败", "error") } finally { setLoading(false) }
  }, [toast])

  useEffect(() => { loadConfig() }, [loadConfig])

  const handleSave = async () => { try { await runtimeSave(); toast("已保存", "success") } catch { toast("保存失败", "error") } }
  const handleSelfCheck = async () => { try { const data = await runtimeSelfCheck(); setCheck(data); toast("自检完成", "success") } catch { toast("自检失败", "error") } }
  const handleRefreshCheck = async () => { try { await runtimeRefreshSelfCheck(); toast("自检刷新完成", "success"); handleSelfCheck() } catch { toast("操作失败", "error") } }
  const handleAutoSaveToggle = async (v: boolean) => { try { await runtimeAutoSave(v, autoInterval); setAutoSave(v); toast(v ? "自动保存已开启" : "自动保存已关闭", "success") } catch { toast("操作失败", "error") } }
  const handleRebuildVectors = async () => { try { await rebuildVectors(); toast("向量重建已触发", "success") } catch { toast("操作失败", "error") } }

  return (
    <div className="space-y-5">
      <Card
        title="运行时配置"
        actions={<><Button variant="outline" size="sm" onClick={handleSave}><Save className="h-3 w-3" />保存</Button><Button variant="outline" size="sm" onClick={loadConfig}><RefreshCw className="h-3 w-3" />刷新</Button></>}
      >
        {loading ? <Loading />
        : !config ? <p className="text-sm text-default-500">无法加载配置</p>
        : (
          <div className="space-y-3">
            <div className="flex items-center justify-between rounded-xl border border-white/10 bg-content1/45 p-3">
              <div>
                <p className="text-sm font-medium">自动保存</p>
                <p className="text-xs text-default-500">定时自动保存运行时数据</p>
              </div>
              <button
                onClick={() => handleAutoSaveToggle(!autoSave)}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${autoSave ? "bg-success" : "bg-default-100/60"}`}
              >
                <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${autoSave ? "translate-x-6" : "translate-x-1"}`} />
              </button>
            </div>
            {autoSave && (
              <div className="flex items-center gap-2">
                <span className="text-xs text-default-500">间隔(秒):</span>
                <input type="number" value={autoInterval} onChange={(e) => setAutoInterval(Number(e.target.value))} className="h-7 w-24 rounded-md border border-white/10 bg-transparent px-2 text-xs text-default-900" />
              </div>
            )}
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" onClick={handleRebuildVectors}><Database className="h-4 w-4" />重建向量索引</Button>
            </div>
          </div>
        )}
      </Card>

      <Card title="系统自检" actions={<><Button variant="outline" size="sm" onClick={handleSelfCheck}><CheckCircle className="h-3 w-3" />自检</Button><Button variant="outline" size="sm" onClick={handleRefreshCheck}><AlertTriangle className="h-3 w-3" />刷新自检</Button></>}>
        {check !== null ? (
          <pre className="max-h-80 overflow-auto rounded-xl border border-white/10 bg-content1/45 p-4 text-xs leading-relaxed whitespace-pre-wrap font-mono">
            {JSON.stringify(check, null, 2)}
          </pre>
        ) : (
          <p className="text-sm text-default-500">点击"自检"按钮开始检查</p>
        )}
      </Card>
    </div>
  )
}