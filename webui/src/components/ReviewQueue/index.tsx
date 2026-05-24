import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { HelpCircle, ListChecks } from "lucide-react"
import Card from "@/components/Card"
import Button from "@/components/Button"
import { useToast } from "@/components/Toast"
import {
  approveCard,
  deleteCard,
  fetchCard,
  fetchCards,
  fetchReviewStats,
  hasPermission,
  questionCard,
  rejectCard,
  updateCard,
  type AuthUser,
} from "@/lib/api"
import StatusTabs from "./StatusTabs"
import FilterBar, { type FilterBarHandle } from "./FilterBar"
import ListPane from "./ListPane"
import BulkActionBar from "./BulkActionBar"
import DetailPane from "./DetailPane"
import EditorModal from "./EditorModal"
import KeyboardHelp from "./KeyboardHelp"
import QuestionReasonModal from "./QuestionReasonModal"
import useKeyboardShortcuts from "./useKeyboardShortcuts"
import { STATUS_LABEL } from "./constants"
import { apiErrorMessage, listToText, splitEditList } from "./utils"
import type { ActionKey, BulkProgress, CardItem, EditForm, ReviewStats } from "./types"

const PAGE_SIZE = 50

const EMPTY_FORM: EditForm = {
  title: "",
  category: "",
  question: "",
  answer: "",
  search_terms: "",
  aliases: "",
  rlcraft_version: "",
  answer_type: "other",
  valid_status: "active",
  evidence: "",
}

const INITIAL_BULK: BulkProgress = { total: 0, done: 0, failed: [], action: null, running: false }

export default function ReviewQueue({ user }: { user: AuthUser }) {
  const { toast } = useToast()
  const filterBarRef = useRef<FilterBarHandle>(null)

  // 列表 & 分页
  const [cards, setCards] = useState<CardItem[]>([])
  const [loading, setLoading] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [hasMore, setHasMore] = useState(false)
  const [offset, setOffset] = useState(0)

  // 筛选
  const [filter, setFilter] = useState<string>("pending")
  const [keyword, setKeyword] = useState("")
  const [category, setCategory] = useState("")
  const [editorScope, setEditorScope] = useState("exclude_self")
  const [sortBy, setSortBy] = useState("updated_desc")
  const [legacyOnly, setLegacyOnly] = useState(false)
  const [sourceGroupId, setSourceGroupId] = useState("")
  const [sourceGroupName, setSourceGroupName] = useState("")

  // 状态计数
  const [stats, setStats] = useState<ReviewStats | null>(null)

  // 选中 + 多选
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [bulkMode, setBulkMode] = useState(false)
  const [bulkSelection, setBulkSelection] = useState<Set<string>>(new Set())
  const [bulkProgress, setBulkProgress] = useState<BulkProgress>(INITIAL_BULK)

  // 单卡操作锁 & 编辑
  const [busyIds, setBusyIds] = useState<Set<string>>(new Set())
  const [editingCard, setEditingCard] = useState<CardItem | null>(null)
  const [editForm, setEditForm] = useState<EditForm>(EMPTY_FORM)
  const [questionTarget, setQuestionTarget] = useState<CardItem | null>(null)
  const [questionReason, setQuestionReason] = useState("")

  // 移动端栈式：手机端选中后切到详情
  const [mobileDetailOpen, setMobileDetailOpen] = useState(false)
  const [showHelp, setShowHelp] = useState(false)

  const canEdit = hasPermission(user, "knowledge.edit")
  const canApprove = hasPermission(user, "review.approve")
  const canReject = hasPermission(user, "review.reject")
  const canDelete = hasPermission(user, "knowledge.delete")

  // ===== Data fetching =====
  const buildParams = useCallback(
    (extra?: Record<string, unknown>) => ({
      status: filter,
      keyword: keyword.trim(),
      category,
      editor_scope: editorScope,
      sort_by: sortBy,
      ...(legacyOnly ? { source: "legacy_import" } : {}),
      ...(sourceGroupId ? { source_group_id: sourceGroupId } : {}),
      ...extra,
    }),
    [category, editorScope, filter, keyword, legacyOnly, sortBy, sourceGroupId],
  )

  const loadList = useCallback(
    async (silent = false, append = false, currentOffset = 0) => {
      if (!silent) {
        if (append) setLoadingMore(true)
        else setLoading(true)
      }
      try {
        const data = (await fetchCards({ ...buildParams(), limit: PAGE_SIZE, offset: currentOffset })) as {
          items?: CardItem[]
          cards?: CardItem[]
          count?: number
        }
        const items = data.items || data.cards || []
        const fetched = Array.isArray(items) ? items : []
        setCards((prev) => (append ? [...prev, ...fetched] : fetched))
        setHasMore(fetched.length >= PAGE_SIZE)
        setOffset(currentOffset + fetched.length)
      } catch {
        if (!silent) toast("加载审核队列失败", "error")
      } finally {
        if (!silent) {
          setLoading(false)
          setLoadingMore(false)
        }
      }
    },
    [buildParams, toast],
  )

  const loadStats = useCallback(async (silent = false) => {
    try {
      const data = await fetchReviewStats()
      const raw = (data?.stats || {}) as Record<string, number>
      setStats({
        pending: raw.pending || 0,
        needs_answer: raw.needs_answer || 0,
        similar: raw.similar || 0,
        conflict: raw.conflict || 0,
        processing: raw.processing || 0,
        approved: raw.approved || 0,
        rejected: raw.rejected || 0,
        ai_rejected: raw.ai_rejected || 0,
        superseded: raw.superseded || 0,
      })
    } catch {
      if (!silent) toast("加载状态计数失败", "error")
    }
  }, [toast])

  // 初次 & 筛选改变 → 重新拉
  useEffect(() => {
    setOffset(0)
    setSelectedId(null)
    void loadList(false, false, 0)
  }, [loadList])

  useEffect(() => {
    void loadStats(true)
  }, [loadStats])

  // processing tab / 列表中存在 processing 时 3s 轮询
  useEffect(() => {
    const needPoll = filter === "processing" || cards.some((card) => card.review_status === "processing")
    if (!needPoll) return
    const timer = window.setInterval(() => {
      void loadList(true, false, 0)
      void loadStats(true)
    }, 3000)
    return () => window.clearInterval(timer)
  }, [filter, cards, loadList, loadStats])

  // ===== Selection helpers =====
  const selectedCard = useMemo(() => cards.find((card) => String(card.id) === selectedId) || null, [cards, selectedId])

  const setCardBusy = (id: string, busy: boolean) => {
    setBusyIds((prev) => {
      const next = new Set(prev)
      if (busy) next.add(id)
      else next.delete(id)
      return next
    })
  }

  // preserveAs 不为空时表示卡片只是变成了终态（rejected/approved），仍要在其他主卡的相似工作台里看到（用于灰显）；
  // 不传则表示彻底删除，完全从 similar_cards 数组里移除。
  const removeCardFromList = useCallback((id: string, preserveAs?: string) => {
    setCards((items) =>
      items
        .filter((card) => String(card.id) !== id)
        .map((card) => ({
          ...card,
          similar_cards: Array.isArray(card.similar_cards)
            ? preserveAs
              ? card.similar_cards.map((item) =>
                  String(item.id || "") === id ? { ...item, review_status: preserveAs } : item,
                )
              : card.similar_cards.filter((item) => String(item.id || "") !== id)
            : card.similar_cards,
        })),
    )
    setBulkSelection((prev) => {
      if (!prev.has(id)) return prev
      const next = new Set(prev)
      next.delete(id)
      return next
    })
    setSelectedId((current) => (current === id ? null : current))
  }, [])

  const selectCard = useCallback((card: CardItem) => {
    setSelectedId(String(card.id))
    if (window.matchMedia("(max-width: 767px)").matches) setMobileDetailOpen(true)
  }, [])

  // ===== Single-card actions =====
  const handleApprove = useCallback(async (id: string) => {
    if (busyIds.has(id)) return
    const previousCards = cards
    setCardBusy(id, true)
    setCards((items) => items.map((card) => (String(card.id) === id ? { ...card, review_status: "processing" } : card)))
    try {
      const result = (await approveCard(id)) as { success?: boolean; error?: string; queued?: boolean }
      if (result.success === false) throw new Error(result.error || "审核通过失败")
      toast(result.queued ? "已进入处理中，后台写入知识库" : "已通过，后台写入知识库", "success")
      if (filter !== "processing") removeCardFromList(id, "approved")
      void loadStats(true)
    } catch (error) {
      setCards(previousCards)
      toast(apiErrorMessage(error, "操作失败"), "error")
    } finally {
      setCardBusy(id, false)
    }
  }, [busyIds, cards, filter, loadStats, removeCardFromList, toast])

  const handleReject = useCallback(async (id: string) => {
    if (busyIds.has(id)) return
    const previousCards = cards
    setCardBusy(id, true)
    setCards((items) => items.map((card) => (String(card.id) === id ? { ...card, review_status: "processing" } : card)))
    try {
      const result = (await rejectCard(id)) as { success?: boolean; error?: string }
      if (result.success === false) throw new Error(result.error || "审核拒绝失败")
      toast("已拒绝", "info")
      removeCardFromList(id, "rejected")
      void loadStats(true)
    } catch (error) {
      setCards(previousCards)
      toast(apiErrorMessage(error, "操作失败"), "error")
    } finally {
      setCardBusy(id, false)
    }
  }, [busyIds, cards, loadStats, removeCardFromList, toast])

  const handleQuestion = useCallback((id: string) => {
    if (busyIds.has(id)) return
    const target = cards.find((card) => String(card.id) === id)
    if (!target) {
      toast("卡片不存在或列表已刷新，请重新选择", "error")
      return
    }
    if (target && String(target.review_status || "") === "approved") {
      toast("已入库卡片不能直接置为疑问，请先撤回入库", "error")
      return
    }
    setQuestionTarget(target)
    setQuestionReason("")
  }, [busyIds, cards, toast])

  const closeQuestionReason = useCallback(() => {
    setQuestionTarget(null)
    setQuestionReason("")
  }, [])

  const submitQuestionReason = useCallback(async () => {
    if (!questionTarget) return
    const id = String(questionTarget.id)
    if (busyIds.has(id)) return
    if (String(questionTarget.review_status || "") === "approved") {
      toast("已入库卡片不能直接置为疑问，请先撤回入库", "error")
      return
    }
    const reason = questionReason.trim()
    const previousCards = cards
    setCardBusy(id, true)
    try {
      const result = (await questionCard(id, reason)) as { success?: boolean; error?: string }
      if (result.success === false) throw new Error(result.error || "置疑问失败")
      toast("已转入【疑问】Tab，未写入检索库", "success")
      closeQuestionReason()
      if (filter !== "needs_answer") removeCardFromList(id, "needs_answer")
      else void loadList(true, false, 0)
      void loadStats(true)
    } catch (error) {
      setCards(previousCards)
      toast(apiErrorMessage(error, "操作失败"), "error")
    } finally {
      setCardBusy(id, false)
    }
  }, [busyIds, cards, closeQuestionReason, filter, loadList, loadStats, questionReason, questionTarget, removeCardFromList, toast])

  const handleDelete = useCallback(async (id: string, options?: { skipConfirm?: boolean }) => {
    if (busyIds.has(id)) return
    const target = cards.find((card) => String(card.id) === id)
    const status = String(target?.review_status || "")
    if (!options?.skipConfirm) {
      const message =
        status === "approved"
          ? "确定删除这条已入库知识吗？将从检索库中移除，对应审核记录会标记为已拒绝。"
          : status === "needs_answer"
            ? "确定彻底丢弃这条疑问吗？记录会被物理删除，「已拒绝」Tab 也找不到。\n如果只是 AI 误判 / 不采纳，请改用「标为无效」。"
            : "确定彻底删除这条审核记录吗？此操作不可恢复。"
      if (!window.confirm(message)) return
    }
    const previousCards = cards
    setCardBusy(id, true)
    removeCardFromList(id)
    try {
      await deleteCard(id)
      toast(status === "approved" ? "已删除入库知识" : "已删除", "success")
      void loadStats(true)
    } catch (error) {
      setCards(previousCards)
      toast(apiErrorMessage(error, "操作失败"), "error")
    } finally {
      setCardBusy(id, false)
    }
  }, [busyIds, cards, loadStats, removeCardFromList, toast])

  // ===== Editor =====
  const openEditor = useCallback((card: CardItem) => {
    setEditingCard(card)
    setEditForm({
      title: card.title || "",
      category: card.category || "",
      question: card.question || "",
      answer: card.answer || "",
      search_terms: listToText(card.search_terms),
      aliases: listToText(card.aliases),
      rlcraft_version: card.rlcraft_version || "",
      answer_type: card.answer_type || "other",
      valid_status: card.valid_status || "active",
      evidence: card.evidence || "",
    })
  }, [])

  const openEditorById = useCallback(async (id: string) => {
    const local = cards.find((card) => String(card.id) === id)
    if (local) {
      openEditor(local)
      return
    }
    if (busyIds.has(id)) return
    setCardBusy(id, true)
    try {
      const data = (await fetchCard(id)) as { card?: CardItem }
      if (!data.card) throw new Error("卡片不存在")
      openEditor(data.card)
    } catch (error) {
      toast(apiErrorMessage(error, "加载卡片失败"), "error")
    } finally {
      setCardBusy(id, false)
    }
  }, [busyIds, cards, openEditor, toast])

  const closeEditor = useCallback(() => setEditingCard(null), [])
  const handleEditChange = useCallback((key: keyof EditForm, value: string) => {
    setEditForm((prev) => ({ ...prev, [key]: value }))
  }, [])

  const handleSaveEdit = useCallback(async () => {
    if (!editingCard) return
    const id = String(editingCard.id)
    if (busyIds.has(id)) return
    setCardBusy(id, true)
    try {
      const payload = {
        ...editForm,
        search_terms: splitEditList(editForm.search_terms),
        aliases: splitEditList(editForm.aliases),
      }
      const result = (await updateCard(id, payload)) as { mode?: string; card?: CardItem }
      if (result.mode === "revision") {
        toast("已创建修订版，进入待审核", "success")
      } else if (editingCard.review_status === "needs_answer" && editForm.answer.trim()) {
        toast("已补充答案，进入审核流程", "success")
      } else {
        toast("已保存修改", "success")
      }
      closeEditor()
      void loadList(true, false, 0)
      void loadStats(true)
    } catch (error) {
      toast(apiErrorMessage(error, "保存失败"), "error")
    } finally {
      setCardBusy(id, false)
    }
  }, [busyIds, closeEditor, editForm, editingCard, loadList, loadStats, toast])

  // ===== Bulk actions =====
  const runBulk = useCallback(async (action: ActionKey) => {
    if (bulkSelection.size === 0 || bulkProgress.running) return
    if (action === "edit") return
    const ids = Array.from(bulkSelection)
    const verb = action === "approve" ? "通过" : action === "reject" ? "拒绝" : "删除"
    const confirmMessage = action === "delete"
      ? `确定批量删除 ${ids.length} 张卡片吗？已通过卡片会从检索库移除并标记为已拒绝；其他卡片永久删除，无法恢复。`
      : `确定批量${verb} ${ids.length} 张卡片吗？`
    if (!window.confirm(confirmMessage)) return
    const failed: { id: string; reason: string }[] = []
    setBulkProgress({ total: ids.length, done: 0, failed: [], action, running: true })
    for (let index = 0; index < ids.length; index++) {
      const id = ids[index]
      setCardBusy(id, true)
      try {
        let preserveAs: string | undefined
        if (action === "approve") {
          const result = (await approveCard(id)) as { success?: boolean; error?: string }
          if (result.success === false) throw new Error(result.error || "失败")
          preserveAs = "approved"
        } else if (action === "reject") {
          const result = (await rejectCard(id)) as { success?: boolean; error?: string }
          if (result.success === false) throw new Error(result.error || "失败")
          preserveAs = "rejected"
        } else {
          await deleteCard(id)
        }
        removeCardFromList(id, preserveAs)
      } catch (error) {
        failed.push({ id, reason: apiErrorMessage(error, "失败") })
      } finally {
        setCardBusy(id, false)
        setBulkProgress((prev) => ({ ...prev, done: prev.done + 1, failed: [...failed] }))
      }
    }
    setBulkProgress((prev) => ({ ...prev, running: false }))
    if (failed.length === 0) {
      toast(`批量${verb}完成 (${ids.length})`, "success")
      setBulkSelection(new Set())
    } else {
      toast(`完成 ${ids.length - failed.length} 张，失败 ${failed.length} 张`, "error")
      setBulkSelection(new Set(failed.map((item) => item.id)))
    }
    void loadStats(true)
  }, [bulkProgress.running, bulkSelection, loadStats, removeCardFromList, toast])

  const toggleBulk = useCallback((id: string) => {
    setBulkSelection((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
    setBulkMode(true)
  }, [])

  const toggleAll = useCallback(() => {
    if (cards.length === 0) return
    const allSelected = cards.every((card) => bulkSelection.has(String(card.id)))
    if (allSelected) {
      setBulkSelection(new Set())
    } else {
      setBulkSelection(new Set(cards.map((card) => String(card.id))))
      setBulkMode(true)
    }
  }, [bulkSelection, cards])

  const clearSelection = useCallback(() => {
    setBulkSelection(new Set())
    setBulkMode(false)
  }, [])

  // ===== Filters =====
  const clearFilters = useCallback(() => {
    setKeyword("")
    setCategory("")
    setEditorScope("exclude_self")
    setSortBy("updated_desc")
    setLegacyOnly(false)
    setSourceGroupId("")
    setSourceGroupName("")
  }, [])

  const handleFilterByGroup = useCallback((groupId: string, groupName: string) => {
    setSourceGroupId(groupId)
    setSourceGroupName(groupName)
    setSelectedId(null)
    toast(`已过滤到来源：${groupName || groupId}`, "info")
  }, [toast])

  // ===== Keyboard shortcuts =====
  const currentIndex = useMemo(() => cards.findIndex((card) => String(card.id) === selectedId), [cards, selectedId])

  useKeyboardShortcuts({
    enabled: !editingCard && !questionTarget && !showHelp,
    onNext: () => {
      if (cards.length === 0) return
      const nextIndex = currentIndex < 0 ? 0 : Math.min(cards.length - 1, currentIndex + 1)
      selectCard(cards[nextIndex])
    },
    onPrev: () => {
      if (cards.length === 0) return
      const prevIndex = currentIndex <= 0 ? 0 : currentIndex - 1
      selectCard(cards[prevIndex])
    },
    onApprove: () => {
      if (!selectedCard || !canApprove) return
      void handleApprove(String(selectedCard.id))
    },
    onReject: () => {
      if (!selectedCard || !canReject) return
      void handleReject(String(selectedCard.id))
    },
    onDelete: () => {
      if (!selectedCard || !canDelete) return
      void handleDelete(String(selectedCard.id))
    },
    onEdit: () => {
      if (!selectedCard || !canEdit) return
      openEditor(selectedCard)
    },
    onToggleBulk: () => setBulkMode((value) => !value),
    onToggleSelectCurrent: () => {
      if (!selectedCard) return
      toggleBulk(String(selectedCard.id))
    },
    onFocusSearch: () => filterBarRef.current?.focusKeyword(),
    onEscape: () => {
      if (bulkSelection.size > 0) {
        clearSelection()
        return
      }
      if (mobileDetailOpen) setMobileDetailOpen(false)
    },
    onShowHelp: () => setShowHelp(true),
  })

  const filterLabel = STATUS_LABEL[filter] || filter

  return (
    <Card
      title={
        <span className="flex items-center gap-2">
          <ListChecks className="h-4 w-4 text-primary" />
          审核工作台
        </span>
      }
      className="review-queue-panel flex max-h-none min-h-0 flex-col overflow-hidden md:h-full"
      actions={
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setShowHelp(true)}
            title="键盘快捷键 (按 ? 也可打开)"
          >
            <HelpCircle className="h-3.5 w-3.5" />
            快捷键
          </Button>
        </div>
      }
    >
      <div className="flex min-h-0 flex-1 flex-col gap-3">
        <StatusTabs
          filter={filter}
          stats={stats}
          loading={loading}
          legacyOnly={legacyOnly}
          onChangeFilter={(status) => {
            setFilter(status)
            setSelectedId(null)
          }}
          onToggleLegacy={() => setLegacyOnly((value) => !value)}
          onRefresh={() => {
            void loadList(false, false, 0)
            void loadStats(true)
          }}
        />
        <FilterBar
          ref={filterBarRef}
          keyword={keyword}
          category={category}
          editorScope={editorScope}
          sortBy={sortBy}
          sourceGroupId={sourceGroupId}
          sourceGroupName={sourceGroupName}
          onKeywordChange={setKeyword}
          onCategoryChange={setCategory}
          onEditorScopeChange={setEditorScope}
          onSortByChange={setSortBy}
          onClearSourceFilter={() => {
            setSourceGroupId("")
            setSourceGroupName("")
          }}
          onClearAll={clearFilters}
        />

        <div className="grid min-h-0 flex-1 gap-3 md:grid-cols-[minmax(20rem,1fr)_minmax(0,2fr)]">
          <div className={`flex min-h-0 flex-col ${mobileDetailOpen ? "hidden md:flex" : "flex"}`}>
            <ListPane
              cards={cards}
              loading={loading}
              selectedId={selectedId}
              bulkSelection={bulkSelection}
              bulkMode={bulkMode}
              currentUserId={user.id}
              hasMore={hasMore}
              loadingMore={loadingMore}
              filterLabel={filterLabel}
              onSelect={selectCard}
              onToggleBulk={toggleBulk}
              onToggleAll={toggleAll}
              onLoadMore={() => void loadList(false, true, offset)}
            />
            <BulkActionBar
              user={user}
              selectionCount={bulkSelection.size}
              progress={bulkProgress}
              onRun={runBulk}
              onClear={clearSelection}
            />
          </div>
          <div className={`flex min-h-0 flex-col ${mobileDetailOpen ? "flex" : "hidden md:flex"}`}>
            <DetailPane
              card={selectedCard}
              user={user}
              busyIds={busyIds}
              mobileMode={mobileDetailOpen}
              onBack={() => setMobileDetailOpen(false)}
              onApprove={handleApprove}
              onReject={handleReject}
              onQuestion={handleQuestion}
              onDelete={handleDelete}
              onEdit={openEditor}
              onEditById={openEditorById}
              onFilterByGroup={handleFilterByGroup}
            />
          </div>
        </div>
      </div>

      {editingCard && (
        <EditorModal
          card={editingCard}
          form={editForm}
          busy={busyIds.has(String(editingCard.id))}
          onChange={handleEditChange}
          onClose={closeEditor}
          onSave={handleSaveEdit}
        />
      )}
      {questionTarget && (
        <QuestionReasonModal
          card={questionTarget}
          value={questionReason}
          busy={busyIds.has(String(questionTarget.id))}
          onChange={setQuestionReason}
          onClose={closeQuestionReason}
          onSubmit={submitQuestionReason}
        />
      )}
      <KeyboardHelp open={showHelp} onClose={() => setShowHelp(false)} />
    </Card>
  )
}
