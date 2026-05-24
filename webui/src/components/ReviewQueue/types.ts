export interface SimilarCardItem {
  id?: string | number
  title?: string
  category?: string
  question?: string
  answer?: string
  tags?: string[]
  search_terms?: string[]
  aliases?: string[]
  rlcraft_version?: string
  answer_type?: string
  valid_status?: string
  review_status?: string
  score?: number
}

export interface CardItem {
  id: string | number
  title?: string
  category?: string
  question?: string
  answer?: string
  tags?: string[]
  search_terms?: string[]
  aliases?: string[]
  platform?: string
  source_platform?: string
  rlcraft_version?: string
  answer_type?: string
  valid_status?: string
  confidence?: number
  review_status: string
  source_stream_id?: string
  source_group_id?: string
  source_group_name?: string
  paragraph_hash?: string
  evidence?: string
  ai_review_status?: string
  ai_review_reason?: string
  ai_review_score?: number
  ai_review_issues?: string[]
  created_at?: number
  updated_at?: number
  reviewed_at?: number
  reviewed_by?: string
  reviewed_by_name?: string
  last_editor_id?: string
  last_editor_name?: string
  revision_of_card_id?: number
  edit_count?: number
  similar_cards?: SimilarCardItem[]
}

export interface EditForm {
  title: string
  category: string
  question: string
  answer: string
  search_terms: string
  aliases: string
  rlcraft_version: string
  answer_type: string
  valid_status: string
  evidence: string
}

export type ActionKey = "approve" | "reject" | "delete" | "edit" | "question"

export interface ActionSpec {
  label: string
  tooltip: string
  variant: "primary" | "secondary" | "outline" | "ghost" | "destructive" | "success"
}

export interface BulkProgress {
  total: number
  done: number
  failed: { id: string; reason: string }[]
  action: ActionKey | null
  running: boolean
}

export interface ReviewStats {
  pending: number
  needs_answer: number
  similar: number
  conflict: number
  processing: number
  approved: number
  rejected: number
  ai_rejected: number
  superseded?: number
}

export type EditorScope = "exclude_self" | "self" | "others" | "all"
