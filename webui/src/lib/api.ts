import axios from "axios"

const TOKEN_KEY = "gk-webui-token"

const api = axios.create({
  baseURL: "/api/game-knowledge",
  timeout: 30000,
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY)
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

export interface AuthGroup {
  id: string
  name: string
  description?: string
  permissions: string[]
}

export interface AuthUser {
  id: string
  username: string
  display_name?: string
  status: string
  groups: AuthGroup[]
  permissions: string[]
  created_at?: number
  updated_at?: number
  last_login_at?: number
  last_login_ip?: string
  failed_login_count?: number
  locked_until?: number | null
  token_version?: number
  risk_flags?: string[]
  risk_level?: "normal" | "medium" | "high"
}

export interface AuthSettings {
  allow_registration: boolean
  captcha_placeholder_enabled: boolean
  registration_captcha_enabled?: boolean
  registration_captcha_group_id?: string
  registration_captcha_cooldown_seconds?: number
  registration_captcha_ttl_seconds?: number
  default_registration_group: string
}

export interface AuthAuditEvent {
  id: number
  user_id?: string
  username?: string
  event: string
  ip?: string
  user_agent?: string
  success?: number
  detail?: string
  created_at?: number
}

export function getAuthToken(): string {
  return localStorage.getItem(TOKEN_KEY) || ""
}

export function setAuthToken(token: string) {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

export function hasPermission(user: AuthUser | null | undefined, permission: string): boolean {
  const permissions = user?.permissions || []
  return permissions.includes("*") || permissions.includes(permission)
}

export async function fetchBootstrapStatus(): Promise<{ success: boolean; has_users: boolean; groups: AuthGroup[]; settings: AuthSettings }> {
  const { data } = await api.get("/auth/bootstrap")
  return data
}

export async function bootstrapAdmin(payload: {
  username: string
  password: string
  display_name?: string
}): Promise<{ success: boolean; token: string; user: AuthUser }> {
  const { data } = await api.post("/auth/bootstrap", payload)
  return data
}

export async function login(payload: {
  username: string
  password: string
}): Promise<{ success: boolean; token: string; user: AuthUser }> {
  const { data } = await api.post("/auth/login", payload)
  return data
}

export async function register(payload: {
  username: string
  password: string
  display_name?: string
  captcha?: string
}): Promise<{ success: boolean; token: string; user: AuthUser }> {
  const { data } = await api.post("/auth/register", payload)
  return data
}

export async function requestRegistrationCaptcha(payload: {
  username: string
}): Promise<{ success: boolean; message?: string; cooldown_seconds?: number; ttl_seconds?: number; cooldown_remaining?: number }> {
  const { data } = await api.post("/auth/captcha/request", payload)
  return data
}

export async function fetchMe(): Promise<{ success: boolean; user: AuthUser }> {
  const { data } = await api.get("/auth/me")
  return data
}

export async function updateProfile(payload: { display_name: string }): Promise<{ success: boolean; user: AuthUser }> {
  const { data } = await api.patch("/auth/profile", payload)
  return data
}

export async function changePassword(payload: {
  current_password: string
  new_password: string
}): Promise<{ success: boolean; token: string; user: AuthUser }> {
  const { data } = await api.post("/auth/password", payload)
  return data
}

export async function fetchUsers(params: Record<string, unknown> = {}): Promise<{ success: boolean; users: AuthUser[]; groups: AuthGroup[] }> {
  const { data } = await api.get("/auth/users", { params })
  return data
}

export async function fetchAuthAudit(limit = 100, params: Record<string, unknown> = {}): Promise<{ success: boolean; events: AuthAuditEvent[] }> {
  const { data } = await api.get("/auth/audit", { params: { limit, ...params } })
  return data
}

export async function createUser(payload: {
  username: string
  password: string
  display_name?: string
  group_ids: string[]
  status?: string
}): Promise<{ success: boolean; user: AuthUser }> {
  const { data } = await api.post("/auth/users", payload)
  return data
}

export async function updateUser(id: string, payload: Record<string, unknown>): Promise<{ success: boolean; user: AuthUser }> {
  const { data } = await api.patch(`/auth/users/${id}`, payload)
  return data
}

export async function deleteUser(id: string): Promise<unknown> {
  const { data } = await api.delete(`/auth/users/${id}`)
  return data
}

export async function fetchMyHistory(limit = 50): Promise<unknown> {
  const { data } = await api.get("/me/history", { params: { limit } })
  return data
}

/* ====== 仪表盘 ====== */
export async function fetchStats(): Promise<Record<string, number>> {
  const { data } = await api.get("/stats")
  return data
}

/* ====== 搜索 ====== */
export async function searchMemory(query: string, limit = 20, options: Record<string, unknown> = {}): Promise<unknown> {
  const { data } = await api.post("/search", { query, limit, ...options })
  return data
}

export async function randomSearchMemory(limit = 20): Promise<unknown> {
  const { data } = await api.get("/search/random", { params: { limit } })
  return data
}

export async function fetchSearchHitCard(hash: string): Promise<unknown> {
  const { data } = await api.get(`/search/hits/${encodeURIComponent(hash)}/card`)
  return data
}

export async function questionSearchHit(hash: string, payload: Record<string, unknown>): Promise<unknown> {
  const { data } = await api.post(`/search/hits/${encodeURIComponent(hash)}/question`, payload)
  return data
}

export async function updateSearchHit(hash: string, payload: Record<string, unknown>): Promise<unknown> {
  const { data } = await api.patch(`/search/hits/${encodeURIComponent(hash)}`, payload)
  return data
}

export async function deleteSearchHit(hash: string): Promise<unknown> {
  const { data } = await api.delete(`/search/hits/${encodeURIComponent(hash)}`)
  return data
}

/* ====== 写入 ====== */
export interface IngestPayload {
  external_id?: string
  source_type?: string
  text: string
  chat_id?: string
  tags?: string[]
  metadata?: Record<string, unknown>
  relations?: string[]
  entities?: string[]
}

export async function ingestMemory(payload: IngestPayload): Promise<unknown> {
  const { data } = await api.post("/ingest", payload)
  return data
}

export async function uploadFiles(files: File[], payload: {
  tags?: string[]
  metadata?: Record<string, unknown>
} = {}): Promise<unknown> {
  const form = new FormData()
  files.forEach((f) => form.append("files", f))
  if (payload.tags) form.append("tags", JSON.stringify(payload.tags))
  if (payload.metadata) form.append("metadata", JSON.stringify(payload.metadata))
  const { data } = await api.post("/ingest/upload", form, {
    headers: { "Content-Type": "multipart/form-data" },
    timeout: 120000,
  })
  return data
}

/* ====== 审核队列 ====== */
export async function fetchCards(params?: Record<string, unknown>): Promise<unknown> {
  const { data } = await api.get("/cards", { params })
  return data
}

export interface ReviewStats {
  success?: boolean
  total?: number
  stats: Record<string, number>
}

export async function fetchReviewStats(): Promise<ReviewStats> {
  const { data } = await api.get("/cards/stats")
  return data
}

export async function fetchCardGroups(params?: Record<string, unknown>): Promise<unknown> {
  const { data } = await api.get("/cards/groups", { params })
  return data
}

export async function fetchCard(id: string): Promise<unknown> {
  const { data } = await api.get(`/cards/${id}`)
  return data
}

export async function approveCard(id: string): Promise<unknown> {
  const { data } = await api.post(`/cards/${id}/approve`)
  return data
}

export async function updateCard(id: string, payload: Record<string, unknown>): Promise<unknown> {
  const { data } = await api.patch(`/cards/${id}`, payload)
  return data
}

export async function rejectCard(id: string): Promise<unknown> {
  const { data } = await api.post(`/cards/${id}/reject`)
  return data
}

export async function questionCard(id: string, reason?: string): Promise<unknown> {
  const { data } = await api.post(`/cards/${id}/question`, { reason: reason || "" })
  return data
}

export async function deleteCard(id: string): Promise<unknown> {
  const { data } = await api.delete(`/cards/${id}`)
  return data
}

export async function fetchQualityTuningCards(params?: Record<string, unknown>): Promise<unknown> {
  const { data } = await api.get("/quality-tuning/cards", { params })
  return data
}

export async function fetchQualityTuningTasks(limit = 20): Promise<unknown> {
  const { data } = await api.get("/quality-tuning/tasks", { params: { limit } })
  return data
}

export async function runQualityTuning(payload?: Record<string, unknown>): Promise<unknown> {
  const { data } = await api.post("/quality-tuning/run", payload || {}, { timeout: 180000 })
  return data
}

/* ====== 图谱 ====== */
export async function fetchGraph(limit = 200): Promise<unknown> {
  const { data } = await api.get("/graph", { params: { limit } })
  return data
}

export async function searchGraph(query: string, limit = 50): Promise<unknown> {
  const { data } = await api.get("/graph/search", { params: { query, limit } })
  return data
}

export async function createGraphNode(name: string, type = "entity"): Promise<unknown> {
  const { data } = await api.post("/graph/node", { name, type })
  return data
}

export async function deleteGraphNode(name: string): Promise<unknown> {
  const { data } = await api.delete("/graph/node", { data: { name } })
  return data
}

export async function renameGraphNode(name: string, new_name: string): Promise<unknown> {
  const { data } = await api.post("/graph/node/rename", { old_name: name, name, new_name })
  return data
}

export async function createGraphEdge(subject: string, predicate: string, object: string, weight?: number): Promise<unknown> {
  const { data } = await api.post("/graph/edge", { subject, predicate, object, weight, confidence: weight })
  return data
}

export async function deleteGraphEdge(subject: string, predicate: string, object: string, hash?: string): Promise<unknown> {
  const { data } = await api.delete("/graph/edge", { data: { subject, predicate, object, hash } })
  return data
}

/* ====== 来源 ====== */
export async function fetchSources(params?: Record<string, unknown>): Promise<unknown> {
  const { data } = await api.get("/sources", { params })
  return data
}

export async function deleteSource(source: string): Promise<unknown> {
  const { data } = await api.post("/sources/delete", { source })
  return data
}

/* ====== 维护 V5 ====== */
export async function fetchRecycleBin(): Promise<unknown> {
  const { data } = await api.get("/recycle-bin")
  return data
}

export async function v5Action(action: string, payload?: Record<string, unknown>): Promise<unknown> {
  const { data } = await api.post(`/v5/${action}`, payload || {})
  return data
}

/* ====== 运行时 ====== */
export async function fetchRuntimeConfig(): Promise<unknown> {
  const { data } = await api.get("/config")
  return data
}

export async function runtimeSave(): Promise<unknown> {
  const { data } = await api.post("/save")
  return data
}

export async function runtimeSelfCheck(deep = false): Promise<unknown> {
  const { data } = await api.post("/self-check", { deep })
  return data
}

export async function runtimeRefreshSelfCheck(): Promise<unknown> {
  const { data } = await api.post("/refresh-self-check")
  return data
}

export async function runtimeAutoSave(auto: boolean, interval?: number): Promise<unknown> {
  const { data } = await api.post("/config/auto-save", { auto, interval })
  return data
}

export async function rebuildVectors(): Promise<unknown> {
  const { data } = await api.post("/vectors/rebuild")
  return data
}

/* ====== 调优 ====== */
export async function fetchTuningProfile(): Promise<unknown> {
  const { data } = await api.get("/tuning/profile")
  return data
}

export async function fetchTuningTasks(limit = 50): Promise<unknown> {
  const { data } = await api.get("/tuning/tasks", { params: { limit } })
  return data
}

export async function createTuningTask(payload: Record<string, unknown>): Promise<unknown> {
  const { data } = await api.post("/tuning/create-task", payload)
  return data
}

export async function cancelTuningTask(taskId: string): Promise<unknown> {
  const { data } = await api.post("/tuning/cancel-task", { task_id: taskId })
  return data
}

export async function applyBestTuningProfile(taskId: string): Promise<unknown> {
  const { data } = await api.post("/tuning/apply-best", { task_id: taskId })
  return data
}

export async function applyTuningProfile(profile: Record<string, unknown>): Promise<unknown> {
  const { data } = await api.post("/tuning/apply-profile", { profile, reason: "webui" })
  return data
}

export async function rollbackTuningProfile(): Promise<unknown> {
  const { data } = await api.post("/tuning/rollback")
  return data
}

/* ====== 删除管理 ====== */
export async function previewDelete(mode: string, selector?: Record<string, unknown>): Promise<unknown> {
  const { data } = await api.post("/delete/preview", { mode, selector: selector || {} })
  return data
}

export async function executeDelete(mode: string, selector?: Record<string, unknown>): Promise<unknown> {
  const { data } = await api.post("/delete/execute", { mode, selector: selector || {} })
  return data
}

export async function restoreDelete(operationId: string): Promise<unknown> {
  const { data } = await api.post("/delete/restore", { operation_id: operationId })
  return data
}

export async function fetchDeleteOperations(limit = 50, mode?: string): Promise<unknown> {
  const { data } = await api.get("/delete/operations", { params: { limit, ...(mode ? { mode } : {}) } })
  return data
}

export async function fetchDeleteOperation(operationId: string): Promise<unknown> {
  const { data } = await api.get(`/delete/operations/${operationId}`)
  return data
}

/* ====== 导入任务管理 ====== */
export async function fetchImportSettings(): Promise<unknown> {
  const { data } = await api.get("/import/settings")
  return data
}

export async function fetchImportTasks(limit = 50): Promise<unknown> {
  const { data } = await api.get("/import/tasks", { params: { limit } })
  return data
}

export async function fetchImportTask(taskId: string, includeChunks = false): Promise<unknown> {
  const { data } = await api.get(`/import/tasks/${taskId}`, {
    params: { include_chunks: includeChunks ? "true" : "false" },
  })
  return data
}

export async function fetchImportFiles(taskId: string): Promise<unknown> {
  const { data } = await api.get("/import/files", { params: { task_id: taskId } })
  return data
}

export async function fetchImportChunks(
  taskId: string,
  fileId: string,
  offset = 0,
  limit = 30,
): Promise<unknown> {
  const { data } = await api.get("/import/chunks", {
    params: { task_id: taskId, file_id: fileId, offset, limit },
  })
  return data
}

export async function cancelImportTask(taskId: string): Promise<unknown> {
  const { data } = await api.post("/import/cancel", { task_id: taskId })
  return data
}

export async function retryImportTask(taskId: string): Promise<unknown> {
  const { data } = await api.post("/import/retry", { task_id: taskId })
  return data
}

// ==================== 公告 ====================

export type AnnouncementSeverity = "info" | "warning" | "critical"
export type AnnouncementStatus = "draft" | "published"

export interface Announcement {
  id: number
  title: string
  content: string
  severity: AnnouncementSeverity
  pinned: boolean
  status: AnnouncementStatus
  starts_at: number | null
  ends_at: number | null
  author_id: string
  author_nickname: string
  created_at: number
  updated_at: number
}

export interface AnnouncementListResponse {
  success: boolean
  items: Announcement[]
  total: number
}

export interface AnnouncementCreatePayload {
  title: string
  content: string
  severity?: AnnouncementSeverity
  pinned?: boolean
  status?: AnnouncementStatus
  starts_at?: number | null
  ends_at?: number | null
}

export async function fetchAnnouncements(params: {
  status?: string
  include_inactive?: boolean
  limit?: number
  offset?: number
} = {}): Promise<AnnouncementListResponse> {
  const { data } = await api.get("/announcements", { params })
  return data
}

export async function fetchActiveAnnouncements(limit = 5): Promise<{ success: boolean; items: Announcement[] }> {
  const { data } = await api.get("/announcements/active", { params: { limit } })
  return data
}

export async function createAnnouncement(payload: AnnouncementCreatePayload): Promise<{ success: boolean; item: Announcement }> {
  const { data } = await api.post("/announcements", payload)
  return data
}

export async function deleteAnnouncement(id: number): Promise<{ success: boolean; deleted: boolean }> {
  const { data } = await api.delete(`/announcements/${id}`)
  return data
}

// ==================== 留言板 ====================

export type BoardThreadStatus = "open" | "forwarded" | "collecting" | "resolved" | "closed"
export type BoardPostSource = "web" | "qq"

export interface BoardPost {
  id: number
  thread_id: number
  author_id: string
  author_nickname: string
  content: string
  reply_to_post_id: number | null
  source: BoardPostSource
  source_user_id: string
  source_message_id: string
  created_at: number
}

export interface BoardThread {
  id: number
  title: string
  author_id: string
  author_nickname: string
  status: BoardThreadStatus
  source_group_id: string | null
  forwarded_at: number | null
  forwarded_message_id: string | null
  forward_target_group_id: string | null
  collected_until: number | null
  collected_message_count: number
  resolved_at: number | null
  resolved_by_id: string | null
  last_reply_at: number | null
  reply_count: number
  created_at: number
  updated_at: number
  posts?: BoardPost[]
}

export interface BoardThreadListResponse {
  success: boolean
  items: BoardThread[]
  total: number
}

export interface BoardResolveResponse {
  success: boolean
  submitted: number
  card_hashes: string[]
  ai_reviewed?: number
  ai_rejected?: number
  error?: string
  note?: string
  thread?: BoardThread
}

export async function fetchBoardThreads(params: {
  status?: string
  limit?: number
  offset?: number
} = {}): Promise<BoardThreadListResponse> {
  const { data } = await api.get("/board/threads", { params })
  return data
}

export async function fetchBoardThread(id: number): Promise<{ success: boolean; item: BoardThread }> {
  const { data } = await api.get(`/board/threads/${id}`)
  return data
}

export async function createBoardThread(payload: { title: string; content: string }): Promise<{ success: boolean; item: BoardThread }> {
  const { data } = await api.post("/board/threads", payload)
  return data
}

export async function deleteBoardThread(id: number): Promise<{ success: boolean; deleted: boolean }> {
  const { data } = await api.delete(`/board/threads/${id}`)
  return data
}

export async function replyBoardThread(id: number, payload: { content: string; reply_to_post_id?: number | null }): Promise<{ success: boolean; item: BoardPost }> {
  const { data } = await api.post(`/board/threads/${id}/posts`, payload)
  return data
}

export async function resolveBoardThread(id: number, payload: { picked_post_ids?: number[] } = {}): Promise<BoardResolveResponse> {
  const { data } = await api.post(`/board/threads/${id}/resolve`, payload)
  return data
}

export async function deleteBoardPost(id: number): Promise<{ success: boolean; deleted: boolean }> {
  const { data } = await api.delete(`/board/posts/${id}`)
  return data
}
