import { useEffect, useState, forwardRef, useImperativeHandle, useRef } from "react"
import { ChevronDown, Filter, SlidersHorizontal, X } from "lucide-react"
import Button from "@/components/Button"
import { CATEGORY_OPTIONS, EDITOR_SCOPE_OPTIONS, FILTER_INPUT_CLASS, SORT_OPTIONS } from "./constants"

export interface FilterBarHandle {
  focusKeyword: () => void
}

interface Props {
  keyword: string
  category: string
  editorScope: string
  sortBy: string
  sourceGroupId: string
  sourceGroupName: string
  onKeywordChange: (value: string) => void
  onCategoryChange: (value: string) => void
  onEditorScopeChange: (value: string) => void
  onSortByChange: (value: string) => void
  onClearSourceFilter: () => void
  onClearAll: () => void
}

// 关键词输入加 300ms debounce，避免逐字符触发请求
const FilterBar = forwardRef<FilterBarHandle, Props>(function FilterBar(props, ref) {
  const [keywordDraft, setKeywordDraft] = useState(props.keyword)
  const [open, setOpen] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => setKeywordDraft(props.keyword), [props.keyword])

  useEffect(() => {
    if (keywordDraft === props.keyword) return
    const timer = window.setTimeout(() => props.onKeywordChange(keywordDraft), 300)
    return () => window.clearTimeout(timer)
  }, [keywordDraft, props])

  useImperativeHandle(ref, () => ({
    focusKeyword: () => {
      setOpen(true)
      window.setTimeout(() => inputRef.current?.focus(), 60)
    },
  }))

  const activeCount = [
    props.keyword.trim(),
    props.category,
    props.editorScope !== "exclude_self" ? props.editorScope : "",
    props.sortBy !== "updated_desc" ? props.sortBy : "",
    props.sourceGroupId,
  ].filter(Boolean).length

  return (
    <div className="grid gap-2">
      {props.sourceGroupId && (
        <div className="flex items-center justify-between gap-2 rounded-md border border-primary/25 bg-primary/8 px-2.5 py-1.5 text-xs">
          <span className="inline-flex items-center gap-1.5 text-primary">
            <Filter className="h-3 w-3" />
            来源过滤：{props.sourceGroupName || props.sourceGroupId}
            <span className="font-mono text-[0.65rem] text-primary/70">#{props.sourceGroupId}</span>
          </span>
          <button
            type="button"
            onClick={props.onClearSourceFilter}
            className="inline-flex h-5 items-center gap-0.5 rounded-md border border-primary/20 px-1.5 text-[0.65rem] text-primary hover:bg-primary/15"
            title="清除来源过滤"
          >
            <X className="h-2.5 w-2.5" />
            取消
          </button>
        </div>
      )}
      <button
        type="button"
        className="flex h-8 w-full items-center justify-between rounded-xl border border-black/10 bg-content1/40 px-3 text-xs font-semibold text-default-700 shadow-sm dark:border-white/10 md:hidden"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
      >
        <span className="inline-flex items-center gap-2">
          <SlidersHorizontal className="h-3.5 w-3.5 text-primary" />
          筛选
          {activeCount > 0 && (
            <span className="rounded-full bg-primary/15 px-1.5 py-0.5 text-[0.62rem] text-primary">{activeCount}</span>
          )}
        </span>
        <ChevronDown className={`h-3.5 w-3.5 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      <div className={`${open ? "grid" : "hidden"} gap-2 rounded-xl border border-black/10 bg-content1/24 p-2 dark:border-white/10 md:grid md:border-0 md:bg-transparent md:p-0 md:grid-cols-[minmax(0,1fr)_8.5rem_8rem_8.5rem_auto]`}>
        <input
          ref={inputRef}
          className={FILTER_INPUT_CLASS}
          value={keywordDraft}
          onChange={(event) => setKeywordDraft(event.target.value)}
          placeholder="关键词 / 标题 / 问题 (按 / 聚焦)"
        />
        <select
          className={FILTER_INPUT_CLASS}
          value={props.category}
          onChange={(event) => props.onCategoryChange(event.target.value)}
          title="按分类筛选"
        >
          <option value="">全部分类</option>
          {CATEGORY_OPTIONS.map((item) => <option key={item} value={item}>{item}</option>)}
        </select>
        <select
          className={FILTER_INPUT_CLASS}
          value={props.editorScope}
          onChange={(event) => props.onEditorScopeChange(event.target.value)}
          title="按修改人筛选"
        >
          {EDITOR_SCOPE_OPTIONS.map((item) => <option key={item.key} value={item.key} title={item.title}>{item.label}</option>)}
        </select>
        <select
          className={FILTER_INPUT_CLASS}
          value={props.sortBy}
          onChange={(event) => props.onSortByChange(event.target.value)}
          title="排序方式"
        >
          {SORT_OPTIONS.map((item) => <option key={item.key} value={item.key}>{item.label}</option>)}
        </select>
        <Button variant="outline" size="sm" onClick={props.onClearAll} title="重置所有筛选条件">清空</Button>
      </div>
    </div>
  )
})

export default FilterBar
