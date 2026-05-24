import type { ActionKey, ActionSpec } from "./types"

export const REVIEW_STATUSES = [
  "pending",
  "needs_answer",
  "similar",
  "conflict",
  "processing",
  "approved",
  "rejected",
  "ai_rejected",
] as const

export const STATUS_LABEL: Record<string, string> = {
  pending: "待审核",
  needs_answer: "疑问",
  similar: "疑似相似",
  conflict: "冲突",
  processing: "处理中",
  approved: "已通过",
  rejected: "已拒绝",
  ai_rejected: "AI已拒绝",
  superseded: "已被替代",
}

export const STATUS_DESCRIPTION: Record<string, string> = {
  pending: "等待人工审核的全新卡片",
  needs_answer: "需要补充答案后才能进入审核流程",
  similar: "与既有卡片高度相似，需要确认是否保留",
  conflict: "与既有卡片产生版本冲突，需要决定是否覆盖",
  processing: "正在写入检索库，串行队列处理中",
  approved: "已通过并入库，可被检索",
  rejected: "已被拒绝，未写入检索库（数据仍可查找）",
  ai_rejected: "AI 自动拒绝，需要人工确认",
  superseded: "已被新版替代，仅保留历史",
}

export const CATEGORY_OPTIONS = ["攻略", "机制", "推荐", "配置", "报错", "装备", "版本", "模组", "掉落", "位置", "其他"]

export const ANSWER_TYPE_OPTIONS = [
  { key: "error_fix", label: "报错修复" },
  { key: "config", label: "配置" },
  { key: "recommendation", label: "推荐" },
  { key: "guide", label: "攻略" },
  { key: "mechanic", label: "机制" },
  { key: "location", label: "位置" },
  { key: "drop", label: "掉落" },
  { key: "other", label: "其他" },
]

export const VALID_STATUS_OPTIONS = [
  { key: "active", label: "有效" },
  { key: "stale", label: "待更新" },
  { key: "deprecated", label: "已过期" },
  { key: "conflict", label: "冲突" },
]

export const EDITOR_SCOPE_OPTIONS = [
  { key: "exclude_self", label: "除本人", title: "包含系统/AI 自动生成和其他用户修改，隐藏自己修改的卡片" },
  { key: "others", label: "其他用户", title: "只看明确由其他用户修改或提交的卡片，不含系统/AI 自动生成" },
  { key: "self", label: "本人", title: "只看自己修改或提交的卡片" },
  { key: "all", label: "全部", title: "显示全部卡片，包括自己修改的卡片" },
]

export const SORT_OPTIONS = [
  { key: "updated_desc", label: "最近更新" },
  { key: "updated_asc", label: "最早更新" },
  { key: "created_desc", label: "最新创建" },
  { key: "created_asc", label: "最早创建" },
  { key: "score_desc", label: "评分高到低" },
  { key: "score_asc", label: "评分低到高" },
  { key: "id_desc", label: "ID 从大到小" },
  { key: "id_asc", label: "ID 从小到大" },
]

// 核心：每个 status × action 的按钮真实含义
// 让用户 hover 时清楚知道按下去到底是“写入检索库”、“仅关闭审核记录”还是“从检索库移除”
export const ACTION_MATRIX: Record<string, Partial<Record<ActionKey, ActionSpec>>> = {
  pending: {
    approve: { label: "通过并入库", tooltip: "标记为已通过，并把这条内容写入检索库；用户搜索时会被检索到。", variant: "success" },
    reject: { label: "不通过", tooltip: "标记为已拒绝，不写入检索库；数据仍保留在【已拒绝】Tab，可以找回。", variant: "destructive" },
    question: {
      label: "疑问",
      tooltip: "把这张卡片转入【疑问】Tab，不写入检索库；用于标记“这条暂时存疑，需要补答案或进一步确认”。\n点击后会弹窗让你填一句疑问理由。",
      variant: "outline",
    },
    delete: { label: "彻底删除记录", tooltip: "从审核库永久删除这条记录，无法恢复（未入库，不影响检索）。", variant: "ghost" },
    edit: { label: "编辑", tooltip: "打开编辑器修改卡片字段；未通过卡片直接原地保存。", variant: "outline" },
  },
  needs_answer: {
    approve: {
      label: "直接入库",
      tooltip:
        "无视答案校验直接通过 —— 适用于：AI 把正常内容误判成疑问、问题本身已是答案、人工判断无需补答即可入库。\n" +
        "→ 标记为已通过并写入检索库（即便 A 字段为空，依然按 Q + 元数据可被搜到）。\n" +
        "想补答案再入库？请先点「编辑」填 A 字段，保存后会自动重走相似度判定。",
      variant: "success",
    },
    edit: {
      label: "编辑（补答案）",
      tooltip: "打开编辑器修改字段。常用于补 A 字段；保存后会自动重新走相似度判定，可能落到待审/相似/疑问。",
      variant: "primary",
    },
    reject: {
      label: "标为无效（AI 误判 / 不采纳）",
      tooltip:
        "这条疑问不应该收录 —— 包括但不限于：AI 把闲聊误判成疑问、问题本身不成立、内容已过时、有更好的卡可参考。\n" +
        "→ 状态改为「已拒绝」，不写入检索库；记录保留，可在【已拒绝】Tab 找回，也方便统计 AI 误判率。\n" +
        "日常关闭疑问优先用这个按钮。",
      variant: "destructive",
    },
    delete: {
      label: "丢弃（永久清除）",
      tooltip:
        "这条数据是垃圾 —— 乱码、重复、测试痕迹、明显的脏数据，不值得留任何审计记录。\n" +
        "→ 从审核库物理删除，不可恢复，「已拒绝」Tab 也找不到。\n" +
        "正常 AI 误判请用左边的「标为无效」，这个按钮只在你想完全抹除这一行时用。",
      variant: "ghost",
    },
  },
  similar: {
    approve: { label: "保留此卡入库", tooltip: "把这张候选卡视为新增内容写入检索库；相似的旧卡需要单独处理。", variant: "success" },
    reject: { label: "不采用此卡", tooltip: "标记为已拒绝、不入库；保留作为历史参考。", variant: "destructive" },
    question: {
      label: "疑问",
      tooltip: "把这张候选卡转入【疑问】Tab，不入库；用于“先挂起、待补答案/进一步确认”。\n点击后会弹窗让你填一句疑问理由。",
      variant: "outline",
    },
    delete: { label: "彻底删除候选", tooltip: "从审核库永久删除这张候选记录，无法恢复。", variant: "ghost" },
    edit: { label: "编辑", tooltip: "打开编辑器修改字段后再决定是否入库。", variant: "outline" },
  },
  conflict: {
    approve: { label: "保留新版入库", tooltip: "把新版本写入检索库；冲突的旧卡会被替代（superseded）。", variant: "success" },
    reject: { label: "不采用新版", tooltip: "标记新版为已拒绝；旧版继续保留在检索库。", variant: "destructive" },
    question: {
      label: "疑问",
      tooltip: "把这张冲突卡转入【疑问】Tab，不入库；旧版仍在检索库不受影响。\n点击后会弹窗让你填一句疑问理由。",
      variant: "outline",
    },
    delete: { label: "彻底删除冲突卡", tooltip: "从审核库永久删除这张冲突记录，无法恢复。", variant: "ghost" },
    edit: { label: "编辑", tooltip: "打开编辑器调整内容后再决定。", variant: "outline" },
  },
  ai_rejected: {
    approve: { label: "推翻 AI，改为通过", tooltip: "覆盖 AI 的判断，标记为已通过并写入检索库。", variant: "success" },
    reject: { label: "确认不收录", tooltip: "确认 AI 的判断，标记为已拒绝；可在【已拒绝】Tab 找回。", variant: "destructive" },
    question: {
      label: "疑问",
      tooltip: "把 AI 拒绝的卡转入【疑问】Tab，不入库；用于“AI 拒得草率，先挂起再说”。\n点击后会弹窗让你填一句疑问理由。",
      variant: "outline",
    },
    delete: { label: "移除审核记录", tooltip: "从审核库永久删除这条记录（未入库，不影响检索）。", variant: "ghost" },
    edit: { label: "编辑", tooltip: "打开编辑器修改字段后再决定是否入库。", variant: "outline" },
  },
  processing: {
    // 不展示按钮；只显示 spinner
  },
  approved: {
    reject: { label: "撤回入库", tooltip: "把这条已入库知识改为已拒绝，但 paragraph 仍保留；建议优先用“从检索库删除”。", variant: "destructive" },
    delete: { label: "从检索库删除", tooltip: "从检索库永久移除对应内容，用户将无法搜索到；审核记录会标记为已拒绝。", variant: "destructive" },
    edit: { label: "新建修订", tooltip: "已通过卡片不可原地编辑；保存后会创建一份修订版，进入待审核。", variant: "outline" },
  },
  rejected: {
    approve: { label: "改判为通过", tooltip: "把这条已拒绝的卡片改判为通过并写入检索库。", variant: "success" },
    delete: { label: "彻底删除记录", tooltip: "从审核库永久删除这条记录，无法恢复。", variant: "ghost" },
    edit: { label: "编辑", tooltip: "重新打开编辑器（保存会重新进入审核流程）。", variant: "outline" },
  },
  superseded: {
    delete: { label: "彻底删除记录", tooltip: "从审核库永久删除这份被替代的历史卡片。", variant: "ghost" },
  },
}

export const SELF_REVIEW_TOOLTIP = "不能审核自己提交/编辑的卡片，请由其他人审核"

export const PROCESSING_HINT = "正在写入检索库，串行队列处理中…"

export const FILTER_INPUT_CLASS =
  "napcat-input h-8 rounded-md px-2 text-xs transition-colors"

export const EDIT_INPUT_CLASS =
  "napcat-input w-full rounded-md px-2 py-1.5 text-sm transition-colors"

export const KEYBOARD_SHORTCUTS: { keys: string; label: string }[] = [
  { keys: "↓ / j", label: "选中下一张" },
  { keys: "↑ / k", label: "选中上一张" },
  { keys: "Space", label: "切换当前行的多选勾选" },
  { keys: "a", label: "通过当前卡片" },
  { keys: "r", label: "拒绝当前卡片" },
  { keys: "e", label: "编辑当前卡片 / 补答案" },
  { keys: "d", label: "删除当前卡片（先弹确认）" },
  { keys: "x", label: "进入/退出多选模式" },
  { keys: "/", label: "聚焦关键词搜索框" },
  { keys: "Esc", label: "退出多选 / 关闭弹窗" },
  { keys: "?", label: "显示此帮助" },
  { keys: "Ctrl/⌘ + Enter", label: "编辑器内：保存" },
]
