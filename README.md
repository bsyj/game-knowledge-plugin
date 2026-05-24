# GameKnowledge

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-GPL--3.0--or--later-blue)](https://spdx.org/licenses/GPL-3.0-or-later.html)
[![MaiBot](https://img.shields.io/badge/MaiBot-1.0.0+-8A2BE2)](https://github.com/MaiM-with-u/MaiBot)
[![SDK](https://img.shields.io/badge/maibot--plugin--sdk-2.0.0+-orange)](https://pypi.org/project/maibot-plugin-sdk/)

面向 [MaiBot](https://github.com/MaiM-with-u/MaiBot) 的工业级游戏知识分析、存储、图谱构建与检索插件。自动从群聊消息中提取结构化游戏知识，构建可检索的知识库，并提供独立 WebUI 管理后台。

## 功能概览

- **群聊消息自动采集** — 按群 ID 白名单自动采集聊天内容，达到阈值触发分析
- **AI 游戏知识提取** — 使用 LLM 从聊天上下文中提取结构化游戏知识（攻略、配置、报错、玩法机制等）
- **AI 预审核** — 自动审核提取的知识质量，分类为待审核/通过/AI 拒绝
- **向量语义搜索** — 基于 FAISS 的向量索引，支持语义检索、时间检索、混合检索和聚合检索
- **知识图谱** — 构建游戏知识实体关系图谱（实体 + 关系 + 段落）
- **Episode 情景记忆** — 长程记忆检索，自动生成 Episode 摘要
- **独立 WebUI** — 内置管理后台，支持知识卡片审核、修订、统计、用户管理
- **留言板与公告系统** — 游戏社区的提问/回答留言板，支持自动转发到 QQ 群求助
- **管理员命令** — 基于 `/gkb` 前缀的命令集，支持搜索、分析、审核、合并、统计

## 快速开始

### 环境要求

- Python 3.10+
- MaiBot v1.0.0+
- Git（用于克隆仓库）

### 安装步骤

```bash
# 1. 进入 MaiBot 插件目录
cd MaiBot/plugins/

# 2. 克隆插件仓库
git clone https://github.com/bsyj/game-knowledge-plugin.git

# 3. 安装 Python 依赖
pip install -r game-knowledge-plugin/requirements.txt

# 4. 在 MaiBot 插件管理中启用本插件（WebUI 或配置文件）
```

安装完成后，插件目录结构如下：

```
game-knowledge-plugin/
├── plugin.py              # 插件入口（MaiBotPlugin 子类）
├── _manifest.json         # 插件元信息
├── config.py              # Pydantic 配置模型
├── config.toml            # 默认配置文件
├── gk_shims/              # SDK 桥接层（日志、消息、LLM 调用）
├── kernel/                # 内核模块（嵌入/检索/存储/策略/工具）
├── web_server.py          # 独立 WebUI 服务端（FastAPI）
├── auth_service.py        # WebUI 认证与权限服务
├── board_service.py       # 留言板业务逻辑
├── board_store.py         # 留言板数据存储
├── announcement_store.py  # 公告数据存储
├── revision_service.py    # 知识修订服务
├── webui/                 # React 前端（TypeScript + Vite）
│   ├── src/               # 前端源码
│   ├── dist/              # 构建产物
│   ├── package.json
│   └── vite.config.ts
├── docs/                  # 附加文档
├── tests/                 # 测试用例
└── requirements.txt       # Python 依赖
```

## 配置说明

插件使用 `config.toml` 进行配置，默认路径为 `plugins/game-knowledge-plugin/config.toml`。以下是完整的配置节说明：

### `[plugin]` — 基础设置

| 键 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `enabled` | bool | `true` | 是否启用插件 |
| `config_version` | str | `"0.1.1"` | 配置版本号 |

### `[storage]` — 存储设置

| 键 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `data_dir` | str | `"data/game-knowledge"` | 游戏知识向量库、元数据数据库和索引文件的存储目录 |

### `[embedding]` — 向量嵌入设置

| 键 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `dimension` | int | `1024` | 嵌入向量维度 |
| `batch_size` | int | `32` | 批量编码的文本数量 |
| `max_concurrent` | int | `5` | 最大并发嵌入请求数 |
| `model_name` | str | `"auto"` | 嵌入模型名称（`auto` 则自动选择） |
| `enable_cache` | bool | `true` | 是否启用嵌入缓存以加速重复查询 |
| `min_train_threshold` | int | `40` | FAISS 索引训练所需的最小向量数 |

### `[web]` — WebUI 设置

| 键 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `enabled` | bool | `true` | 是否启用独立 WebUI 服务 |
| `host` | str | `"127.0.0.1"` | 监听地址（仅本地回环） |
| `port` | int | `5810` | 监听端口 |
| `cleanup_stale_runner_on_port_conflict` | bool | `true` | 端口冲突时是否自动清理旧 Runner |
| `qa_bridge_token` | str | `""` | 供 bs-plugin /QA 桥使用的 token；留空不校验 |

### `[episode]` — Episode 情景记忆设置

| 键 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `enabled` | bool | `false` | 是否启用 Episode 情景记忆检索 |
| `generation_enabled` | bool | `false` | 是否自动生成 Episode 摘要 |
| `pending_batch_size` | int | `12` | 待处理 Episode 的批量大小 |
| `pending_max_retry` | int | `3` | Episode 生成失败的最大重试次数 |

### `[collector]` — 消息采集设置

| 键 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `enabled` | bool | `true` | 是否启用群聊消息自动采集 |
| `allowed_source_group_ids` | list[str] | `[]` | 允许采集的群 ID 白名单。留空表示不限制（采集所有群） |
| `auto_analyze_threshold` | int | `30` | 触发自动分析的消息数阈值 |
| `min_message_length` | int | `3` | 忽略低于此字符数的消息 |
| `context_length` | int | `50` | 缓冲区保留的最大消息数（滑动窗口） |
| `llm_task_name` | str | `"utils"` | 知识提取使用的 MaiBot 模型任务名 |
| `enable_ai_review` | bool | `true` | 是否启用 AI 预审核 |
| `ai_review_task_name` | str | `"utils"` | AI 预审核使用的 MaiBot 模型任务名 |
| `ai_review_error_status` | str | `"pending"` | AI 预审核失败时的降级状态 |

### `[advanced]` — 高级设置

| 键 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `enable_auto_save` | bool | `true` | 是否自动保存向量索引和知识库 |
| `auto_save_interval_minutes` | int | `5` | 自动保存间隔（分钟） |
| `debug` | bool | `false` | 是否启用调试日志 |
| `notify_observer_group` | bool | `false` | 是否向 "观察者" 群发送知识提取通知 |

## 功能详解

### 群聊消息自动采集

插件通过 `HookHandler` 监听 `chat.receive.after_process` 事件，自动收取群聊中的每条消息。采集流程：

1. 检查消息是否来自 `allowed_source_group_ids` 白名单中的群（白名单为空则采集所有群）
2. 过滤长度低于 `min_message_length` 的消息
3. 过滤机器人自身发出的消息
4. 将消息存入滑动窗口缓冲区（最多 `context_length` 条）
5. 当缓冲区消息数达到 `auto_analyze_threshold` 时，自动触发 AI 分析

### AI 游戏知识提取

采集到足够消息后，插件将缓冲区消息打包送给 LLM 进行分析。LLM 会从聊天上下文中提取结构化的游戏知识，输出包含以下字段的知识卡片：

- **标题 (title)** — 知识的概括标题
- **问题 (question)** — 知识回答的问题
- **答案 (answer)** — 具体的解答内容
- **分类 (category)** — 知识分类
- **标签 (tags)** — 关键词标签
- **步骤 (steps)** — 操作步骤列表
- **检索关键词 (search_terms)** — 搜索优化用关键词
- **别名 (aliases)** — 实体别名/俗称
- **答案类型 (answer_type)** — 报错修复/配置/推荐/攻略/机制/位置/掉落/其他

### AI 预审核

提取出的知识卡片会先经过 AI 预审核，自动判断知识质量：

- **通过** — 知识质量合格，直接进入审核队列
- **AI 拒绝** — 知识质量差、重复或无效，标记为 `ai_rejected`
- **降级** — 如果 AI 预审核出错，降级为 `pending` 状态等待人工审核

审核队列统计可通过 `/gkb pending` 命令查看。

### 向量语义搜索

基于 FAISS 的向量索引支持多种检索模式：

| 模式 | 说明 |
| --- | --- |
| `search` | 纯语义搜索，按向量相似度排序 |
| `time` | 按时间排序检索 |
| `hybrid` | 语义 + 时间混合排序 |
| `aggregate` | 聚合检索（默认模式），综合多维度排序 |

LLM 可通过 `query_game_knowledge` Tool 直接调用检索，或在群聊中使用 `/gkb search <关键词>` 命令。

### 知识图谱

插件自动从知识文本中提取实体和关系，构建游戏知识图谱：

- **实体** — 游戏中的物品、角色、Boss、地图、配方等
- **关系** — 实体之间的依赖、获取方式、克制关系等
- **段落** — 知识文本段落，与实体和关系关联

知识图谱数据存储在 `metadata.db` 中，支持图遍历查询。

### Episode 情景记忆

Episode 模块提供长程情景记忆能力。当启用（`episode.enabled`）时：

- 从知识段落中自动聚合生成 Episode 摘要
- Episode 包含时间线、参与者和关键事件
- 支持按时间范围和语义相似度检索历史情境
- 为 LLM 提供更丰富的上下文背景

### 留言板与公告系统

#### 公告 (Announcements)

- 管理员可在 WebUI 中发布公告（标题、正文、严重程度、置顶、生效/失效时间）
- 公告以 Banner 形式在所有页面顶部展示
- 用户可单独关闭每条公告（记录到 localStorage）
- 公告数据存储在插件自带的 `metadata.db` 中

#### 留言板 (Board)

- 任意登录用户可在 WebUI 中创建主题提问
- 支持楼层回复和引用回复
- **无人回应自动转发**：主题创建 2 天后无人回应，bot 自动用 LLM 改写问句并转发到 QQ 群求助
- **群聊答案收集**：转发后自动收集团内后续 20 条消息或 20 分钟内的消息作为候选答案
- 管理员或审核员可将已解决的问答标记入库，转为正式知识卡片

详细说明见 [docs/board.md](docs/board.md)。

## WebUI 使用

### 访问地址

插件启动后，在浏览器中访问：

```
http://127.0.0.1:5810
```

### 首次使用

1. 打开 WebUI 后，使用 QQ 号注册账号
2. 登录后即可使用知识管理、公告、留言板等功能
3. 管理员权限需在数据库或 MaiBot 配置中指定

### 主要功能页面

- **知识卡片管理** — 浏览、搜索、审核、修订知识卡片
- **统计面板** — 查看段落数、实体数、关系数、审核队列状态
- **公告管理** — 发布、查看、删除公告
- **留言板** — 创建主题、回复、标记已解决

### 重新构建前端

如需自定义 WebUI 前端：

```bash
cd webui/
npm install
npm run build
```

构建产物会输出到 `webui/dist/` 目录，插件重启后自动加载最新前端。

前端技术栈：React + TypeScript + Vite。

## 命令列表

插件提供基于 `/gkb` 前缀的管理命令集：

| 命令 | 用法 | 说明 |
| --- | --- | --- |
| `/gkb help` | `/gkb help` | 显示所有可用命令 |
| `/gkb search` | `/gkb search <关键词>` | 搜索游戏知识库 |
| `/gkb analyze` | `/gkb analyze` | 手动触发当前群聊消息分析 |
| `/gkb pending` | `/gkb pending` | 查看待审核卡片数量统计 |
| `/gkb approve` | `/gkb approve <卡片ID>` | 审核通过一张卡片并写入知识库 |
| `/gkb reject` | `/gkb reject <卡片ID>` | 拒绝一张卡片（不删除数据） |
| `/gkb merge` | `/gkb merge <源卡ID> <目标卡ID>` | 把源卡片合并到目标卡片（解决重复知识） |
| `/gkb stats` | `/gkb stats` | 查看知识库统计信息 |

### 命令示例

```
# 搜索"铁砧配方"
/gkb search 铁砧配方

# 查看审核状态
/gkb pending

# 通过第 42 号卡片
/gkb approve 42

# 合并重复卡片：将 15 号卡片合并到 42 号
/gkb merge 15 42

# 查看知识库统计
/gkb stats
```

## 开发指南

### 目录结构

```
game-knowledge-plugin/
├── plugin.py              # 插件入口（GameKnowledgePlugin 类）
├── _manifest.json         # 插件清单（ID、版本、依赖、能力声明）
├── config.py              # Pydantic 配置模型定义
├── config.toml            # 默认配置
├── gk_shims/              # SDK 桥接层
│   ├── logger_shim.py     # 日志桥接
│   ├── message_shim.py    # 消息桥接
│   └── llm_shim.py        # LLM 调用桥接
├── kernel/                # 内核模块
│   ├── core/
│   │   ├── runtime/       # SDK 内核运行时
│   │   ├── utils/         # 工具（分析器、审核队列等）
│   │   └── ...            # 嵌入、检索、存储、策略
│   └── paths.py           # 路径工具
├── web_server.py          # FastAPI WebUI 服务端
├── auth_service.py        # 认证与权限服务
├── board_service.py       # 留言板业务逻辑
├── board_store.py         # 留言板持久化
├── announcement_store.py  # 公告持久化
├── revision_service.py    # 知识修订服务
├── webui/                 # React 前端
│   ├── src/               # 源码目录
│   ├── dist/              # 构建产物
│   └── package.json       # Node 依赖
├── docs/                  # 附加文档
├── tests/                 # 测试用例
└── requirements.txt       # Python 依赖清单
```

### 添加新功能

1. **添加配置项** — 在 `config.py` 对应的配置类中添加 `Field`
2. **添加 LLM Tool** — 在 `plugin.py` 中使用 `@Tool` 装饰器注册新工具
3. **添加命令** — 在 `_cmd_help` 中添加说明，在 `handle_gkb_command` 中添加路由分支
4. **扩展 WebUI** — 修改 `webui/src/` 前端代码，`npm run build` 重新构建
5. **添加 Web API** — 在 `web_server.py` 中注册新路由

### 内核扩展

- **检索策略** — 在 `kernel/core/` 中添加新的检索模式
- **嵌入模型** — 修改 `embedding` 配置节以切换嵌入后端
- **存储后端** — 内核存储模块支持替换不同的向量数据库后端

### 测试

```bash
cd game-knowledge-plugin/
python -m pytest tests/ -v
```

## 依赖

| 依赖 | 版本 | 用途 |
| --- | --- | --- |
| numpy | >=1.20.0 | 数值计算 |
| scipy | >=1.7.0 | 科学计算 |
| networkx | >=3.0.0 | 知识图谱 |
| pyarrow | >=10.0.0 | 数据序列化 |
| pandas | >=1.5.0 | 数据处理 |
| faiss-cpu | >=1.7.0 | 向量索引与检索 |
| fastapi | >=0.100.0 | Web API 框架 |
| uvicorn | >=0.20.0 | ASGI 服务器 |
| pydantic | >=2.0.0 | 数据校验 |
| python-multipart | >=0.0.9 | 表单解析 |
| aiohttp | >=3.8.0 | 异步 HTTP 客户端 |
| nest-asyncio | >=1.5.0 | 嵌套事件循环 |
| openai | >=1.0.0 | LLM API 调用 |
| json-repair | >=0.30.0 | JSON 修复 |
| sentence-transformers | >=2.2.0 | 向量嵌入（可选） |
| psutil | >=5.9.0 | 系统监控 |
| tomlkit | >=0.12.0 | TOML 配置读写 |
| rich | >=14.0.0 | 终端美化输出 |
| tenacity | >=8.0.0 | 重试机制 |
| jieba | >=0.42.1 | 中文分词 |
| maibot-plugin-sdk | >=2.0.0 | MaiBot 插件 SDK |

## 常见问题

**Q: WebUI 页面打不开？**

A: 检查 `web.enabled` 是否为 `true`，确认端口 `5810` 未被其他程序占用。查看 MaiBot 日志中是否有 WebUI 启动失败的提示。

**Q: 知识提取没有触发？**

A: 确认 `collector.enabled` 为 `true`，`allowed_source_group_ids` 包含目标群 ID（或留空），且群聊消息数已达到 `auto_analyze_threshold` 阈值。

**Q: 搜索返回空结果？**

A: 确保已有知识卡片审核通过并写入知识库。使用 `/gkb stats` 查看知识库段落数。新部署的插件需要先在活跃的游戏群中累积聊天数据并触发自动分析。

**Q: 留言板转发失败？**

A: 确保 `allowed_source_group_ids` 至少配置了一个群 ID，且该群最近在 bot 上有过消息记录（需要已注册聊天流）。

## 许可证

本项目基于 GNU General Public License v3.0 或更高版本（GPL-3.0-or-later）开源。详见 [LICENSE](LICENSE)。

---

**作者**: bsyj  
**仓库**: [github.com/bsyj/game-knowledge-plugin](https://github.com/bsyj/game-knowledge-plugin)  
**MaiBot**: [github.com/MaiM-with-u/MaiBot](https://github.com/MaiM-with-u/MaiBot)
