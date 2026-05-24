# 公告与留言板（Board）

> **位置**：仅在 `game_knowledge_plugin` 自带的 WebUI（默认 `http://127.0.0.1:5810`）里使用。需要先在该站点用 QQ 号注册账号并登录。

## 公告（Announcement）

- 入口：左侧导航「公告」。
- 谁能发：仅 `admin` 用户组（权限码 `announcement.publish`）。
- 谁能看：所有 active 用户。Banner 会在每个页面顶部显示当前活跃公告，并支持单条「✕」关闭（写到 localStorage，新公告仍会出现）。
- 字段：标题、正文（纯文本，支持换行）、严重程度（info / warning / critical）、是否置顶、生效/失效时间（均可空）、发布状态（草稿 / 立即发布）。
- 修改策略：**可删不可改**。如需更正请删除后重新发布。
- 数据存放：插件自带的 `metadata.db` 中的 `gk_announcements` 表（不进入主程序 `MaiBot.db`）。

## 留言板（Board）

- 入口：左侧导航「留言板」。
- 谁能发：所有 active 用户（权限码 `board.post`）。
- 谁能标记已解决并入库：`reviewer` / `maintainer` / `admin`（权限码 `board.resolve`）。
- 谁能删主题/楼层：任意登录用户可删自己发的；`maintainer` / `admin` 可删任意（权限码 `board.delete_any`）。
- 楼层结构：平铺楼层 + 引用某楼（一级引用，不嵌套）。
- 数据存放：`gk_board_threads` + `gk_board_posts`。

### 工作流

```
   [群友登录留言板]
         │
         ▼
   创建主题（首楼=问题）            ←──── status=open
         │
   ┌─────┴─────┐
   ▼           ▼
有人回答    2 天无人回应
   │           │
   │           ▼
   │     bot 用 LLM 改写问句，
   │     发到 collector.allowed_source_group_ids[0] 群
   │     status=collecting
   │           │
   │     收集该群后续 20 条群消息 / 20 分钟（先到为准）
   │           │
   ▼           ▼
管理员勾选 / 自动选定的「答案楼层」
         │
         ▼
GameKnowledgeAnalyzer.analyze_messages
         │
         ▼
ReviewQueueService.submit_cards
         │
         ▼
卡片进入待审核队列          ←──── status=resolved → closed
```

### 配置项

复用 `plugins/game_knowledge_plugin/config.toml` 已有字段：

- `collector.allowed_source_group_ids`：bot 转发目标群（取第一个许可群）。
- `collector.llm_task_name`（默认 `utils`）：用于改写问句的模型任务名。

时间阈值（写在 `plugin.py` 顶层常量，需要调整可改源码）：

| 名称 | 默认 | 说明 |
| --- | --- | --- |
| `BOARD_FORWARD_TIMEOUT_SECONDS` | 2 × 24 × 3600（2 天） | 主题创建后多久无人回应触发转发 |
| `BOARD_COLLECT_WINDOW_SECONDS` | 20 × 60（20 分钟） | 转发后收集群消息的时间窗口 |
| `BOARD_COLLECT_MAX_MESSAGES` | 20 | 收集群消息条数上限（先到者停） |
| `BOARD_LOOP_INTERVAL_SECONDS` | 300（5 分钟） | 后台扫描周期 |

### 关键 API（plugin webui 5810 端口）

| Method | Path | 所需权限 | 说明 |
| --- | --- | --- | --- |
| GET | `/api/game-knowledge/announcements` | `announcement.view` | 列表，支持 `status`、`limit`、`offset` |
| GET | `/api/game-knowledge/announcements/active` | `announcement.view` | Banner 用，当前有效公告 |
| POST | `/api/game-knowledge/announcements` | `announcement.publish` | 创建 |
| DELETE | `/api/game-knowledge/announcements/{id}` | `announcement.delete` | 删除 |
| GET | `/api/game-knowledge/board/threads` | `board.view` | 主题列表，支持 `status=active/done/open/forwarded/collecting/resolved/closed` |
| POST | `/api/game-knowledge/board/threads` | `board.post` | 创建主题（含首楼） |
| GET | `/api/game-knowledge/board/threads/{id}` | `board.view` | 主题详情（含楼层） |
| DELETE | `/api/game-knowledge/board/threads/{id}` | `board.view` + 作者或 `board.delete_any` | 删除主题 |
| POST | `/api/game-knowledge/board/threads/{id}/posts` | `board.post` | 回复 / 引用回复 |
| POST | `/api/game-knowledge/board/threads/{id}/resolve` | `board.resolve` | 标记已解决并入库 |
| DELETE | `/api/game-knowledge/board/posts/{id}` | `board.view` + 作者或 `board.delete_any` | 删除楼层 |

### 排错

- **公告 Banner 一直不显示**：检查公告 `status=published` 且 `now ∈ [starts_at, ends_at]`；localStorage `gk-webui-dismissed-announcements` 里如果包含该 id，会被前端隐藏。
- **超时未转发**：先确认 `allowed_source_group_ids` 至少有一个值；其次确认目标群最近在 bot 上发过消息（`chat_manager.resolve_session_ids_by_target` 在 session 未注册时返回空，会跳过本次转发并打日志）。
- **答案没收集到**：要求该群在 `_auth_middleware` 已通过的 plugin runtime hook `chat.receive.after_process` 上能正常触发；如果走的是不同 platform 或不在白名单，hook 会早退。
