import { useState } from "react"
import { Upload, Send, ClipboardPaste, FolderSearch, Loader2, RefreshCw, SlidersHorizontal, Paperclip, FileText } from "lucide-react"
import { ingestMemory, uploadFiles as uploadFilesApi } from "@/lib/api"
import { useToast } from "@/components/Toast"
import Card from "@/components/Card"
import Button from "@/components/Button"
import { cn } from "@/lib/utils"

type ImportMode = "paste" | "upload" | "raw_scan"

const MODE_OPTIONS: { key: ImportMode; label: string; icon: typeof Send }[] = [
  { key: "paste", label: "粘贴导入", icon: ClipboardPaste },
  { key: "upload", label: "上传文件", icon: Upload },
  { key: "raw_scan", label: "本地扫描", icon: FolderSearch },
]

export default function IngestPanel() {
  const { toast } = useToast()

  const [mode, setMode] = useState<ImportMode>("paste")
  const [fileConcurrency, setFileConcurrency] = useState("2")
  const [chunkConcurrency, setChunkConcurrency] = useState("4")
  const [llmEnabled, setLlmEnabled] = useState(false)
  const [chatLog, setChatLog] = useState(false)
  const [strategyOverride, setStrategyOverride] = useState("")
  const [dedupePolicy, setDedupePolicy] = useState("")
  const [forceImport, setForceImport] = useState(false)

  const [pasteName, setPasteName] = useState("")
  const [pasteContent, setPasteContent] = useState("")
  const [uploadFiles, setUploadFiles] = useState<File[]>([])
  const [rawAlias, setRawAlias] = useState("raw")
  const [rawRelativePath, setRawRelativePath] = useState("")
  const [rawGlob, setRawGlob] = useState("**/*.{txt,md,json}")
  const [rawRecursive, setRawRecursive] = useState(true)
  const [creating, setCreating] = useState(false)

  const [result, setResult] = useState<unknown>(null)
  const [history, setHistory] = useState<{ time: string; mode: string; summary: string }[]>([])

  const handleSubmit = async () => {
    setCreating(true)
    try {
      const tags = ["game_knowledge"]
      const metadata: Record<string, unknown> = {
        file_concurrency: parseInt(fileConcurrency) || 2,
        chunk_concurrency: parseInt(chunkConcurrency) || 4,
        llm_enabled: llmEnabled,
        chat_log: chatLog,
        strategy_override: strategyOverride || undefined,
        dedupe_policy: dedupePolicy || undefined,
        force: forceImport,
        mode,
      }

      if (mode === "paste") {
        if (!pasteContent.trim()) { toast("请粘贴内容", "error"); return }
        const data = await ingestMemory({
          external_id: pasteName || "manual_paste",
          source_type: "game_knowledge",
          text: pasteContent,
          tags,
          metadata: { ...metadata, source_name: pasteName || "未命名粘贴" },
        })
        setResult(data)
        toast("写入成功", "success")
        addHistory("粘贴导入", (data as { summary?: string })?.summary || "完成")
        setPasteContent("")
        setPasteName("")
      } else if (mode === "upload") {
        if (uploadFiles.length === 0) { toast("请选择文件", "error"); return }
        const data = await uploadFilesApi(uploadFiles, { tags, metadata })
        setResult(data)
        toast(`上传成功，处理了 ${(data as { files_processed?: number })?.files_processed || 0} 个文件`, "success")
        addHistory("上传文件", `${uploadFiles.length} 个文件`)
        setUploadFiles([])
      } else if (mode === "raw_scan") {
        const scanCfg = JSON.stringify({ alias: rawAlias, path: rawRelativePath, glob: rawGlob, recursive: rawRecursive })
        const data = await ingestMemory({
          external_id: `raw_scan:${rawAlias}:${rawRelativePath || "."}`,
          source_type: "game_knowledge",
          text: scanCfg,
          tags,
          metadata: { ...metadata, scan_config: { alias: rawAlias, path: rawRelativePath, glob: rawGlob, recursive: rawRecursive } },
        })
        setResult(data)
        toast("扫描配置已提交", "info")
        addHistory("本地扫描", `${rawAlias}:${rawRelativePath || "."}`)
      }
    } catch {
      toast("写入失败", "error")
    } finally {
      setCreating(false)
    }
  }

  const addHistory = (modeLabel: string, summary: string) => {
    setHistory((prev) => [
      { time: new Date().toLocaleTimeString("zh-CN"), mode: modeLabel, summary },
      ...prev.slice(0, 19),
    ])
  }

  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        {/* ═══ 左侧: 创建导入任务 ═══ */}
        <div className="order-2 space-y-6 lg:order-1">
          <Card className="rounded-2xl border-white/10 shadow-sm">
            <div className="mb-0 flex items-center gap-2">
              <Upload className="h-4 w-4" />
              <h2 className="text-[0.9375rem] font-semibold tracking-tight">创建导入任务</h2>
            </div>
            <p className="mt-1.5 mb-5 text-xs text-default-500">按"选择导入方式 → 检查公共参数 → 创建任务"的顺序完成导入。</p>

            {/* ── 选择导入方式 ── */}
            <div className="mb-5 space-y-2">
              <label className="text-sm font-medium">选择导入方式</label>
              <div className="inline-flex rounded-full border border-white/10 bg-gradient-to-r from-default-100/50 via-content1/50 to-default-100/30 p-1.5 shadow-inner">
                {MODE_OPTIONS.map((opt) => (
                  <button
                    key={opt.key}
                    onClick={() => setMode(opt.key)}
                    className={cn(
                      "flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-xs font-medium transition-colors",
                      mode === opt.key
                        ? "bg-gradient-to-r from-primary to-primary/80 text-primary-foreground shadow-sm"
                        : "text-default-500 hover:bg-content1/55 hover:text-default-900",
                    )}
                  >
                    <opt.icon className="h-3.5 w-3.5" />
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>

            {/* ── 公共参数 ── */}
            <div className="mb-5 space-y-4 rounded-xl border bg-default-100/20 p-4">
              <div className="rounded-md border border-white/10 bg-content1/55 px-3 py-2">
                <div className="text-sm font-medium">公共参数</div>
                <div className="mt-0.5 text-xs leading-relaxed text-default-500">这些设置会应用到当前导入任务。一般保持默认即可，只在批量导入或排查问题时调整。</div>
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                <div className="grid gap-2 rounded-md border bg-content1/50 p-3 sm:grid-cols-[minmax(0,1fr)_5rem] sm:items-center">
                  <div className="min-w-0">
                    <label className="text-sm font-medium">文件并发数</label>
                    <div className="mt-0.5 text-xs text-default-500">同时处理多少个文件；文件很多时再适当调高。</div>
                  </div>
                  <input type="number" min={1} max={128} value={fileConcurrency} onChange={(e) => setFileConcurrency(e.target.value)}
                    className="h-9 rounded-xl border border-white/10 bg-transparent px-2 text-center text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                  />
                </div>
                <div className="grid gap-2 rounded-md border bg-content1/50 p-3 sm:grid-cols-[minmax(0,1fr)_5rem] sm:items-center">
                  <div className="min-w-0">
                    <label className="text-sm font-medium">分块并发数</label>
                    <div className="mt-0.5 text-xs text-default-500">单个文件内并行处理多少个分块；过高会增加资源占用。</div>
                  </div>
                  <input type="number" min={1} max={256} value={chunkConcurrency} onChange={(e) => setChunkConcurrency(e.target.value)}
                    className="h-9 rounded-xl border border-white/10 bg-transparent px-2 text-center text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                  />
                </div>

                <div className="rounded-md border bg-content1/50 px-2.5 py-2">
                  <label className="flex items-center gap-2 text-sm font-medium leading-tight cursor-pointer">
                    <input type="checkbox" checked={llmEnabled} onChange={(e) => setLlmEnabled(e.target.checked)} className="h-4 w-4 accent-primary" />
                    启用 LLM 抽取
                  </label>
                  <div className="mt-0.5 pl-6 text-[11px] leading-snug text-default-500">需要模型参与抽取，质量更高但耗时更长。</div>
                </div>
                <div className="rounded-md border bg-content1/50 px-2.5 py-2">
                  <label className="flex items-center gap-2 text-sm font-medium leading-tight cursor-pointer">
                    <input type="checkbox" checked={chatLog} onChange={(e) => setChatLog(e.target.checked)} className="h-4 w-4 accent-primary" />
                    按聊天日志解析
                  </label>
                  <div className="mt-0.5 pl-6 text-[11px] leading-snug text-default-500">适合导入聊天记录，会尽量保留时间和对话上下文。</div>
                </div>
              </div>

              <details className="rounded-md border bg-content1/50 p-3 text-sm">
                <summary className="flex cursor-pointer items-center gap-2 text-xs font-medium text-default-500">
                  <SlidersHorizontal className="h-3.5 w-3.5" />
                  高级参数（通常不用修改）
                </summary>
                <div className="mt-3 grid gap-3">
                  <div className="space-y-1">
                    <label className="text-sm font-medium">指定抽取策略</label>
                    <input type="text" value={strategyOverride} onChange={(e) => setStrategyOverride(e.target.value)}
                      className="h-9 w-full rounded-xl border border-white/10 bg-transparent px-3 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="text-sm font-medium">去重策略</label>
                    <input type="text" value={dedupePolicy} onChange={(e) => setDedupePolicy(e.target.value)}
                      className="h-9 w-full rounded-xl border border-white/10 bg-transparent px-3 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                    />
                  </div>
                  <label className="flex items-center gap-2 text-sm cursor-pointer">
                    <input type="checkbox" checked={forceImport} onChange={(e) => setForceImport(e.target.checked)} className="h-4 w-4 accent-primary" />
                    强制导入
                  </label>
                </div>
              </details>
            </div>

            {/* ── 粘贴导入 ── */}
            {mode === "paste" && (
              <div className="mb-5 space-y-3 rounded-xl border bg-content1/50 p-4">
                <div className="text-xs text-default-500">直接粘贴少量文本或 JSON，适合临时补充一段资料。</div>
                <div className="grid gap-3">
                  <div className="space-y-1">
                    <label className="text-sm font-medium">内容名称</label>
                    <input type="text" value={pasteName} onChange={(e) => setPasteName(e.target.value)} placeholder="例如: 武器系统说明"
                      className="h-9 w-full rounded-xl border border-white/10 bg-transparent px-3 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="text-sm font-medium">粘贴内容</label>
                    <textarea value={pasteContent} onChange={(e) => setPasteContent(e.target.value)} rows={8}
                      placeholder="在此粘贴游戏知识文本…"
                      className="w-full rounded-xl border border-white/10 bg-transparent px-3 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary resize-y"
                    />
                  </div>
                </div>
              </div>
            )}

            {/* ── 上传文件 ── */}
            {mode === "upload" && (
              <div className="mb-5 space-y-3 rounded-xl border bg-content1/50 p-4">
                <div className="text-xs text-default-500">选择一个或多个本地文件创建导入任务，适合批量导入资料或聊天记录。</div>
                <div className="grid gap-3">
                  <div className="space-y-1">
                    <label className="text-sm font-medium">文件选择</label>
                    <div className="flex items-center gap-2">
                      <input type="file" multiple accept=".txt,.md,.json,.jsonl,.csv,.log,.html,.htm,.xml"
                        onChange={(e) => setUploadFiles(Array.from(e.target.files ?? []))}
                        className="flex-1 h-9 rounded-xl border border-white/10 bg-transparent px-3 text-sm file:mr-3 file:px-3 file:py-1.5 file:rounded-md file:border-0 file:bg-primary file:text-primary-foreground file:text-xs file:font-medium hover:file:opacity-90 file:cursor-pointer"
                      />
                    </div>
                  </div>
                </div>
                <div className="text-xs text-default-500">
                  <FileText className="mr-1 inline h-3 w-3" />
                  已选择 {uploadFiles.length} 个文件
                  {uploadFiles.length > 0 && (
                    <ul className="mt-1 space-y-0.5">
                      {uploadFiles.map((f, i) => (
                        <li key={i} className="flex items-center gap-1 text-default-500">
                          <Paperclip className="h-3 w-3 flex-shrink-0" />
                          <span className="truncate">{f.name}</span>
                          <span className="text-default-500/60">({(f.size / 1024).toFixed(1)} KB)</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
            )}

            {/* ── 本地扫描 ── */}
            {mode === "raw_scan" && (
              <div className="mb-5 space-y-3 rounded-xl border bg-content1/50 p-4">
                <div className="text-xs text-default-500">扫描目录文件，适合本地批处理</div>
                <div className="grid gap-3">
                  <div className="space-y-1">
                    <label className="text-sm font-medium">路径别名</label>
                    <select value={rawAlias} onChange={(e) => setRawAlias(e.target.value)}
                      className="h-9 w-full rounded-xl border border-white/10 bg-transparent px-3 text-sm cursor-pointer">
                      <option value="raw">raw</option>
                      <option value="data">data</option>
                      <option value="plugins">plugins</option>
                    </select>
                  </div>
                  <div className="space-y-1">
                    <label className="text-sm font-medium">相对路径</label>
                    <div className="text-xs text-default-500">填写相对于路径别名的子路径，不需要填写完整磁盘路径。</div>
                    <input type="text" value={rawRelativePath} onChange={(e) => setRawRelativePath(e.target.value)} placeholder="例如 exports/weekly"
                      className="h-9 w-full rounded-xl border border-white/10 bg-transparent px-3 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="text-sm font-medium">匹配规则（Glob）</label>
                    <input type="text" value={rawGlob} onChange={(e) => setRawGlob(e.target.value)}
                      className="h-9 w-full rounded-xl border border-white/10 bg-transparent px-3 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                    />
                  </div>
                </div>
                <label className="flex items-center gap-2 text-sm cursor-pointer">
                  <input type="checkbox" checked={rawRecursive} onChange={(e) => setRawRecursive(e.target.checked)} className="h-4 w-4 accent-primary" />
                  递归扫描
                </label>
              </div>
            )}

            <Button onClick={handleSubmit} disabled={creating} className="w-full">
              {creating ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Upload className="mr-2 h-4 w-4" />}
              创建导入任务
            </Button>
          </Card>
        </div>

        {/* ═══ 右侧: 写入历史 ═══ */}
        <div className="order-1 space-y-6 lg:order-2">
          <Card className="rounded-2xl border-white/10 bg-content1/60 shadow-sm">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-[0.9375rem] font-semibold tracking-tight">写入历史</h2>
              <span className="rounded-md bg-secondary px-2 py-0.5 text-xs text-default-500">{history.length} 条记录</span>
            </div>
            <p className="mb-4 text-xs text-default-500">查看最近的写入记录，了解导入内容和时间。</p>

            {history.length > 0 ? (
              <div className="max-h-[460px] space-y-2 overflow-y-auto rounded-xl border bg-default-100/5 p-2.5">
                {history.map((h, i) => (
                  <div key={i} className="rounded-xl border bg-content1/55 p-3 text-left transition-all hover:border-default-500/40 hover:bg-default-100/10">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs font-medium">{h.mode}</span>
                      <span className="text-[0.65rem] text-default-500">{h.time}</span>
                    </div>
                    <div className="mt-1 text-xs leading-relaxed text-default-500">{h.summary}</div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="rounded-xl border bg-default-100/20 p-6 text-center">
                <Send className="mx-auto mb-2 h-6 w-6 text-default-500/30" />
                <p className="text-sm text-default-500">暂无写入记录</p>
                <p className="mt-1 text-xs text-default-500">创建导入任务后记录会显示在这里</p>
              </div>
            )}
          </Card>

          {/* ═══ 最新结果 ─══ */}
          {result !== null && (
            <Card className="rounded-2xl border-white/10 bg-content1/60 shadow-sm">
              <div className="mb-3 flex items-center justify-between">
                <h2 className="text-[0.9375rem] font-semibold tracking-tight">最新结果</h2>
                <Button variant="ghost" size="sm" onClick={() => setResult(null)}><RefreshCw className="h-3 w-3" />清除</Button>
              </div>
              <pre className="max-h-72 overflow-auto rounded-xl border border-white/10 bg-content1/45 p-4 text-xs leading-relaxed whitespace-pre-wrap font-mono">
                {JSON.stringify(result, null, 2)}
              </pre>
            </Card>
          )}
        </div>
      </div>
    </div>
  )
}