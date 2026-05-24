# GameKnowledge

GameKnowledge 是一个 MaiBot 插件，用来把游戏群聊里的攻略、配置、报错、机制和问答整理成可审核、可检索、可被 LLM 调用的知识库。插件内置独立 WebUI，支持知识卡片审核、搜索修订、公告、留言板、用户管理和运行时维护。

适合的场景：

- 游戏群里经常出现重复问题，希望 Bot 能逐步沉淀答案。
- 群聊里有大量经验内容，希望自动提取为结构化知识卡片。
- 需要一个给管理员/审核员使用的 Web 管理后台。

## 功能

- 自动采集群聊消息，达到阈值后调用 MaiBot 的 LLM 能力提取知识。
- AI 预审核知识卡片，降低人工审核压力。
- 通过 FAISS、关键词和图谱信息进行知识检索。
- 提供 `query_game_knowledge` 等 Tool，供 MaiBot 在对话中调用知识库。
- 提供 `/gkb` 命令，支持搜索、分析、审核、合并和统计。
- 内置 WebUI：仪表盘、知识检索、审核队列、导入、来源管理、公告、留言板、用户管理。
- 留言板支持无人回复后转发到群聊收集答案，再由审核员入库。

## 环境要求

- MaiBot 1.0.0 或更高版本。
- Python 3.12 推荐，至少应与 MaiBot 主程序运行环境一致。
- `maibot-plugin-sdk` 2.0.0 或更高版本。
- 如需从源码构建 WebUI，需要 Node.js 20+ 和 npm。

依赖以 `requirements.txt` 为准。若你的 MaiBot 使用 `uv` 管理环境，推荐继续使用 `uv` 安装和测试。

## 安装

### 方式一：使用发布包

发布包应包含已经构建好的 `webui/dist/` 目录。把插件目录放到 MaiBot 的 `plugins/` 下即可：

```bash
MaiBot/
└── plugins/
    └── game-knowledge-plugin/
        ├── plugin.py
        ├── _manifest.json
        ├── config.toml
        ├── requirements.txt
        └── webui/dist/
```

然后在 MaiBot 的 Python 环境里安装插件依赖：

```bash
cd MaiBot
uv pip install -r plugins/game-knowledge-plugin/requirements.txt
```

如果你的项目没有使用 `uv`：

```bash
python -m pip install -r plugins/game-knowledge-plugin/requirements.txt
```

重启 MaiBot 后，在插件管理中启用 GameKnowledge。

### 方式二：源码安装

```bash
cd MaiBot/plugins
git clone <本仓库地址> game-knowledge-plugin

cd ../
uv pip install -r plugins/game-knowledge-plugin/requirements.txt

cd plugins/game-knowledge-plugin/webui
npm install
npm run build
```

构建完成后确认存在 `plugins/game-knowledge-plugin/webui/dist/index.html`，再重启 MaiBot。

## 最小配置

配置文件是插件目录下的 `config.toml`。默认配置已经可以启动，但正式使用前建议至少修改群白名单和 WebUI 监听地址。

```toml
[plugin]
enabled = true
config_version = "0.1.2"

[storage]
data_dir = "data/game-knowledge"

[web]
enabled = true
host = "127.0.0.1"
port = 5810
cleanup_stale_runner_on_port_conflict = true

[collector]
enabled = true
allowed_source_group_ids = []
auto_analyze_threshold = 30
min_message_length = 3
context_length = 50
llm_task_name = "utils"
enable_ai_review = true
ai_review_task_name = "utils"
ai_review_error_status = "pending"
```

### 必改项

`collector.allowed_source_group_ids`

群 ID 白名单。默认是空数组，表示不限制采集范围，也就是 Bot 能收到的群聊都可能被采集分析。公开部署或多群运行时强烈建议改成自己的目标群：

```toml
allowed_source_group_ids = ["123456789", "987654321"]
```

`web.host`

默认 `127.0.0.1` 只允许本机访问 WebUI，适合本地部署。如果你要从局域网访问，可以改为：

```toml
host = "0.0.0.0"
```

如果开放到公网，请务必放在反向代理、访问控制或 VPN 后面。

`collector.llm_task_name` 和 `collector.ai_review_task_name`

这两个值对应 MaiBot 模型配置中的任务名。默认使用 `utils`。如果你的 MaiBot 没有这个任务，请改成你实际可用的任务名。

## 完整配置说明

| 配置 | 默认值 | 说明 |
| --- | --- | --- |
| `plugin.enabled` | `true` | 是否启用插件 |
| `plugin.config_version` | `"0.1.2"` | 配置模板版本 |
| `storage.data_dir` | `"data/game-knowledge"` | 插件数据库、索引和缓存目录 |
| `embedding.dimension` | `1024` | 向量维度，需要与实际 embedding 后端一致 |
| `embedding.batch_size` | `32` | 批量 embedding 数量 |
| `embedding.max_concurrent` | `5` | 最大并发 embedding 请求 |
| `embedding.model_name` | `"auto"` | embedding 模型名，`auto` 表示跟随运行时选择 |
| `embedding.enable_cache` | `true` | 是否启用 embedding 缓存 |
| `embedding.min_train_threshold` | `40` | FAISS 索引训练阈值 |
| `web.enabled` | `true` | 是否启动独立 WebUI |
| `web.host` | `"127.0.0.1"` | WebUI 监听地址 |
| `web.port` | `5810` | WebUI 监听端口 |
| `web.cleanup_stale_runner_on_port_conflict` | `true` | 同一 MaiBot 旧 Runner 占用端口时自动清理 |
| `episode.enabled` | `false` | 是否启用 Episode 情景检索 |
| `episode.generation_enabled` | `false` | 是否自动生成 Episode 摘要 |
| `episode.pending_batch_size` | `12` | Episode 待处理批量大小 |
| `episode.pending_max_retry` | `3` | Episode 生成重试次数 |
| `collector.enabled` | `true` | 是否采集群聊消息 |
| `collector.allowed_source_group_ids` | `[]` | 允许采集的群 ID；留空表示不限制 |
| `collector.auto_analyze_threshold` | `30` | 缓冲消息达到多少条后自动分析 |
| `collector.min_message_length` | `3` | 忽略过短消息 |
| `collector.context_length` | `50` | 每个群保留的上下文消息数量 |
| `collector.llm_task_name` | `"utils"` | 知识提取使用的 MaiBot 模型任务 |
| `collector.enable_ai_review` | `true` | 是否启用 AI 预审核 |
| `collector.ai_review_task_name` | `"utils"` | AI 预审核使用的 MaiBot 模型任务 |
| `collector.ai_review_error_status` | `"pending"` | 预审核失败时写入的状态 |
| `advanced.enable_auto_save` | `true` | 是否定期保存索引和运行时状态 |
| `advanced.auto_save_interval_minutes` | `5` | 自动保存间隔 |
| `advanced.debug` | `false` | 是否输出调试日志 |
| `advanced.notify_observer_group` | `false` | 是否发送观察通知 |

## 首次使用 WebUI

插件启动后访问：

```text
http://127.0.0.1:5810
```

第一次进入 WebUI 时会出现初始化页面，创建第一个管理员账号。后续可以在“用户管理”里创建审核员或普通用户。

常见用户组：

- `admin`：拥有全部管理权限。
- `reviewer`：可审核、修订和处理留言板。
- `viewer`：只读和普通留言权限。

WebUI 登录 token 存在浏览器本地存储中。修改密码后，旧 token 会失效。

## 使用命令

插件提供 `/gkb` 命令：

| 命令 | 示例 | 说明 |
| --- | --- | --- |
| `/gkb help` | `/gkb help` | 查看帮助 |
| `/gkb search <关键词>` | `/gkb search 铁砧配方` | 搜索知识库 |
| `/gkb analyze` | `/gkb analyze` | 手动分析当前群缓存消息 |
| `/gkb pending` | `/gkb pending` | 查看待审核统计 |
| `/gkb approve <卡片ID>` | `/gkb approve 42` | 审核通过并写入知识库 |
| `/gkb reject <卡片ID>` | `/gkb reject 42` | 拒绝卡片 |
| `/gkb merge <源ID> <目标ID>` | `/gkb merge 15 42` | 合并重复卡片 |
| `/gkb stats` | `/gkb stats` | 查看知识库统计 |

## 推荐工作流

1. 在 `config.toml` 中填写目标群 `allowed_source_group_ids`。
2. 启动 MaiBot，让插件开始采集群聊。
3. 当消息达到 `auto_analyze_threshold` 后，插件自动生成候选知识卡片。
4. 管理员或审核员在 WebUI 的“审核队列”中审核卡片。
5. 审核通过的卡片会进入知识库，可被 `/gkb search` 和 LLM Tool 检索。
6. 发现重复或错误时，在 WebUI 中修订、合并或删除。

## 留言板和公告

留言板用于收集用户问题：

- 登录用户可以创建主题和回复。
- 主题长时间无人回应时，插件可转发到配置的目标群收集答案。
- 审核员可以把已解决主题整理为知识卡片入库。

公告用于 WebUI 内通知：

- 管理员可以发布公告。
- 支持严重程度、置顶、生效时间和失效时间。
- 普通用户可以阅读并关闭公告横幅。

更多留言板说明见 [docs/board.md](docs/board.md)。

## 数据和隐私

插件会在 `storage.data_dir` 下保存数据库、向量索引、缓存和导入数据。默认目录是：

```text
plugins/game-knowledge-plugin/data/game-knowledge
```

请不要把运行后的 `data/`、数据库文件、日志文件、`.env`、本地备份和用户上传文件提交到公开仓库。仓库的 `.gitignore` 已默认忽略这些运行时数据。

公开发布前建议执行：

```bash
git status --short
rg -n "你的群号|你的QQ|token|secret|password|api_key|Authorization|Bearer" .
```

测试文件中出现的示例账号、示例密码和示例群号只用于自动化测试，不应替换为真实数据。

## 开发

Python 测试：

```bash
cd MaiBot/plugins/game-knowledge-plugin
uv run --project ../.. python -m pytest tests -v
```

卡片操作手动验证脚本：

```bash
cd MaiBot/plugins/game-knowledge-plugin
../../.venv/Scripts/python.exe tests/test_card_operations.py
```

Linux/macOS 可改为：

```bash
../../.venv/bin/python tests/test_card_operations.py
```

前端构建：

```bash
cd MaiBot/plugins/game-knowledge-plugin/webui
npm install
npm run build
```

注意：`tests/test_web_api.py` 当前默认跳过，因为它依赖完整 MaiBot 插件运行时和 WebServer 导入环境。需要验证 HTTP API 时，请先在 MaiBot 中启动插件，再结合实际接口或调整测试夹具运行。

## 目录结构

```text
game-knowledge-plugin/
├── plugin.py
├── _manifest.json
├── config.py
├── config.toml
├── requirements.txt
├── web_server.py
├── auth_service.py
├── board_service.py
├── board_store.py
├── announcement_store.py
├── revision_service.py
├── gk_shims/
├── kernel/
├── webui/
│   ├── src/
│   ├── dist/
│   └── package.json
├── docs/
└── tests/
```

## 故障排查

WebUI 打不开：

- 确认 `web.enabled = true`。
- 确认端口没有被占用。
- 确认 `webui/dist/index.html` 存在。
- 查看 MaiBot 日志中的 `GameKnowledge WebUI started` 或启动失败信息。

没有自动提取知识：

- 确认 `collector.enabled = true`。
- 确认目标群在 `allowed_source_group_ids` 中，或该配置为空。
- 确认消息数量达到 `auto_analyze_threshold`。
- 确认 `llm_task_name` 对应的 MaiBot 模型任务可用。

搜索没有结果：

- 新插件需要先审核通过知识卡片。
- 使用 `/gkb stats` 查看段落数和卡片数。
- 在 WebUI 的“审核队列”中确认是否有待审核卡片。

Embedding 报错：

- 确认 MaiBot 提供 `llm.embed` 能力。
- 确认 `embedding.dimension` 与实际 embedding 后端输出维度一致。
- 如使用本地模型，确认 `sentence-transformers` 等依赖已经安装。

## 致谢

感谢 [Mai-with-u/MaiBot](https://github.com/Mai-with-u/MaiBot) 提供插件运行时、SDK 和机器人宿主能力。

感谢 [A-Dawn/A_memorix](https://github.com/A-Dawn/A_memorix/) 在记忆、检索和知识管理方向上的启发与基础工作。

## 许可证

本项目使用 GPL-3.0-or-later。详见 [kernel/LICENSE](kernel/LICENSE) 及相关许可证文件。
