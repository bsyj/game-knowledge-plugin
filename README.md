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
        ├── config.example.toml
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

重启后在插件管理中启用 GameKnowledge。首次加载时 MaiBot 会根据 Pydantic 默认值自动生成 `config.toml`。如需自定义配置，直接编辑该文件即可（`config.example.toml` 是配置模板，列出了所有可配置项）。

### 方式二：源码安装

仓库已经把构建好的 `webui/dist/` 一并提交，clone 之后无需再构建前端：

```bash
cd MaiBot/plugins
git clone https://github.com/bsyj/game-knowledge-plugin.git game-knowledge-plugin

cd ..
uv pip install -r plugins/game-knowledge-plugin/requirements.txt
```

确认存在 `plugins/game-knowledge-plugin/webui/dist/index.html` 后重启 MaiBot 即可。仅当你要修改 WebUI 前端代码时，才需要进入 `webui/` 运行 `npm install && npm run build`。

## 最小配置

MaiBot 首次加载插件时会自动生成 `config.toml`。`config.example.toml` 是配置模板供参考。

默认配置已经可以启动，但正式使用前建议至少修改群白名单和 WebUI 监听地址。

```toml
[plugin]
enabled = true
config_version = "1.0.2"

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

### 自定义知识提取提示词

如果你的群聊主题、服务器规则、整合包版本、黑话或审核标准和默认配置不同，可以直接改插件里的知识提取提示词。

**最常改的文件：**

```text
kernel/core/utils/game_knowledge_analyzer.py
```

> [!TIP]
> **先改这 4 件事：** 识别什么、拒绝什么、怎么写字段、保留哪些群内词。不要一上来改字段名。

#### 最短修改路径

第一次部署时按这个顺序改，通常就能让自动入库质量明显提升：

| 顺序 | 你要解决的问题 | 修改位置 | 改法要点 |
| --- | --- | --- | --- |
| 1 | 只采集目标群 | `config.toml` 的 `collector.allowed_source_group_ids` | 填目标群 ID，避免 Bot 能看到的所有群都被采集 |
| 2 | 用对模型任务 | `collector.llm_task_name` / `collector.ai_review_task_name` | 改成 MaiBot 中实际可用、适合长文本分析的任务名 |
| 3 | 让 AI 懂你的群 | `_LLM_SYSTEM_PROMPT` 开头的角色背景 | 写清游戏名、服务器、版本、玩法阶段、活动/赛季、群内黑话 |
| 4 | 控制入库质量 | `_LLM_SYSTEM_PROMPT` 的“提取策略 / 质量门槛” | 写清哪些内容值得入库，哪些闲聊、广告、交易、猜测要丢弃 |
| 5 | 控制审核松紧 | `_AI_REVIEW_PROMPT` | 想减少垃圾卡就收紧通过标准；想让人工多兜底就放宽拒绝标准 |
| 6 | 提高搜索命中 | `_LLM_SYSTEM_PROMPT` 和 `_polish_search_terms_with_llm()` 的 `prompt` | 强调保留本群简称、别名、报错原文、装备/地图/任务/配置项 |
| 7 | 调整标签体系 | `_TAG_REWRITE` / `_ALLOWED_THEME_TAGS` 和 `MetadataStore._CARD_TAG_REWRITE` / `_ALLOWED_CARD_THEME_TAGS` | 只有需要新增稳定标签时才改；两处要同步，否则标签可能被过滤 |

#### 提示词地图

`game_knowledge_analyzer.py` 里最关键的是这 3 处：

| 提示词 | 作用 | 什么时候改 |
| --- | --- | --- |
| `_LLM_SYSTEM_PROMPT` | 决定从群聊里提取哪些知识卡片，以及 `title`、`question`、`answer`、`category`、`search_terms` 等字段怎么写 | 必改。想适配自己的游戏、服务器或群黑话，先改这里 |
| `_AI_REVIEW_PROMPT` | 决定卡片进入待审核、待补答，还是被 AI 预拒绝 | 建议改。垃圾卡多就收紧；有价值问题被误拒就放宽 |
| `_polish_search_terms_with_llm()` 里的 `prompt` | 精修 `search_terms`，影响检索命中和召回 | 搜不到群内简称、别名、报错原文时改这里 |

其他较少需要改动的 LLM 提示词：

| 文件 | 用途 |
| --- | --- |
| `plugin.py` 的 `_llm_polish_board_question()` | 留言板问题转发到 QQ 群前的口语化改写 |
| `kernel/core/utils/summary_importer.py` 的 `SUMMARY_PROMPT_TEMPLATE` | 从历史聊天记录批量导入知识 |
| `kernel/core/utils/episode_segmentation_service.py` | Episode 情景摘要切分 |
| `kernel/core/strategies/factual.py` | 实体和三元组抽取 |

#### 写提示词时的检查清单

让提示词更稳定，建议每次都补齐下面几块：

- **领域背景**：游戏名、服务器名、整合包/版本、区服、赛季、玩法阶段。
- **高价值内容**：攻略、机制、配置、报错、掉落、位置、装备/角色/阵容推荐、版本差异。
- **拒绝内容**：闲聊、表情、吵架、广告、交易、隐私、无结论争论、低置信猜测。
- **群内词表**：简称、别名、黑话、配置项、指令、报错原文、地图/任务/Boss/装备名。
- **字段约束**：明确 `question` 必须是完整问题，`answer` 必须自包含，`search_terms` 必须是短关键词。
- **脱敏样例**：放 3 到 6 条真实群聊风格的问答样例，比抽象规则更能稳住输出。

建议优先复用现有字段：`title`、`question`、`answer`、`steps`、`tags`、`search_terms`、`aliases`、`category`、`answer_type`、`valid_status`、`rlcraft_version`、`evidence`。

`rlcraft_version` 是历史兼容字段，虽然名字保留，但现在可当作“游戏版本 / 服务器版本 / 区服 / 平台 / 赛季 / 活动版本”使用。不要轻易改字段名；新增持久化字段需要同步修改数据库存储、审核队列、WebUI 展示和测试，否则字段可能在入库或展示时丢失。

#### 推荐改写骨架

可以把 `_LLM_SYSTEM_PROMPT` 的开头改成这种结构，再按你的群替换占位内容：

```text
你是【游戏名/服务器名】玩家社群知识提取专家。你的任务是把 QQ 群聊内容整理成结构化问答卡片，供 replyer AI 回答玩家问题。

群聊背景：
- 游戏/服务器：【写清游戏、服务器、区服、整合包、版本】
- 高频主题：【写 8 到 15 个最常见主题，例如装备、附魔、配置、报错、地图、掉落、活动、版本差异】
- 群内黑话：【写简称、别名、模组名、指令、配置键、Boss 名、地图名】

优先提取：
1. 玩家明确提问且有人回答的 Q&A。
2. 玩家描述问题，后续有人给出解决方案的隐含问答。
3. 多人讨论后形成共识的机制、配置、版本差异。
4. 有价值但暂时没有答案的问题，只在 question 足够明确时标记 needs_answer=true。

必须拒绝：
- 闲聊、玩笑、情绪、吵架、广告、交易、隐私、群管理通知。
- 没有结论的争论、低置信猜测、缺上下文的“这个怎么弄”。

输出要求：
- question 必须是完整、可搜索、玩家会自然提问的问题。
- answer 必须自包含，replyer AI 拿着就能直接回答玩家。
- search_terms 只放短关键词、别名、报错原文、配置项和核心名词。
- 输出只能是 JSON，不要 markdown 或解释文字。
```

#### 修改后怎么验证

改完提示词后建议先跑一次冒烟测试：

```bash
uv run --project ../.. python -m pytest tests/test_production_smoke.py -v
```

然后用少量脱敏聊天记录触发一次分析，重点看审核队列里的 4 件事：

- `question` 是否完整，不依赖上下文。
- `answer` 是否能直接回答玩家。
- `category` / `answer_type` 是否符合你的分类习惯。
- `search_terms` 是否保留了群内简称、别名、报错原文和关键物品名。

#### 可复制提示词参考

默认提示词已经泛化为通用游戏社群版本，适合大多数游戏群直接使用。你也可以只复制其中的结构，再把例子换成自己的群聊样例。

<details>
<summary>默认知识提取提示词</summary>

```text
你是通用游戏社群知识提取专家。把 QQ 群聊内容整理成结构化问答卡片，供 replyer AI 回答玩家问题。

不要预设具体游戏类型；请以群聊里出现的游戏名、服务器名、平台、区服、版本、赛季、活动、角色、装备、地图、玩法系统和群内黑话为准。

提取策略（按优先级）
1. 显式问答：玩家直接问、有人直接答，提取 Q&A。
2. 推荐/建议：玩家问“xxx推荐什么”“用什么角色/装备/卡组/阵容/设置/路线”，Q=推荐问题，A=推荐选项。
3. 隐含问答：玩家陈述问题、他人给出方案，Q=概括问题，A=方案。
4. 讨论结论：多人讨论产生共识，Q=核心问题，A=结论。
5. 版本/区服/活动差异：同一问题因版本、服务器、平台、赛季或活动不同而答案不同，必须保留差异。
6. 无答案的问题：默认不要提取；只有问题明确、可搜索、后续值得补答时才保留，并设置 answer=""、needs_answer=true、need_review=true。

question 必须是带问句的、可被搜索到的具体问题，不能是话题名称。禁止输出依赖上下文的短问题，如“这个能用吗”“要去那里吗”“这个呢”；必须补全为“某角色当前版本还能用吗”这类完整问题，补不全就丢弃。

answer 必须自包含，replyer AI 拿着就能直接回复玩家。不要输出“群里讨论了设置”“有人说可以有人说不行”这类低信息量答案。

每条 knowledge_cards 包含：
- title: 简短标题，尽量口语化。
- category: 只能从 攻略/机制/推荐/配置/报错/装备/版本/模组/掉落/位置/其他 中选择一个。
- question: 这条知识回答的具体问题。
- answer: 具体答案或建议；若确实是值得补答的问题但群聊没有答案，可以为空字符串。
- steps: 分步骤内容，可选，字符串数组。
- tags: 主题标签数组，只放少量中等粒度主题；不要放游戏名、平台名、群名、游戏知识等全局背景词。
- search_terms: 检索关键词数组，优先放角色名、装备名、道具名、技能名、boss名、地图名、任务名、卡组名、配置项、报错原文关键词、群内简称。
- aliases: 别名数组，只放核心对象真实存在的同义名、英文名、缩写、群内稳定俗称。
- rlcraft_version: 兼容旧字段名；这里填写游戏版本/服务器版本/平台/区服/赛季/活动版本，不确定可留空。
- answer_type: error_fix/config/recommendation/guide/mechanic/location/drop/other。
- valid_status: active/stale/deprecated/conflict。
- source_message_ids: 来源消息 ID 数组。
- confidence: 0~1，越明确越高。
- need_review: true/false。
- needs_answer: true/false。
- evidence: 1 句说明这条知识来自哪些相邻发言，便于审核。

质量门槛：
- answer 为空、“待补充”、“不知道”、“可能吧”时，默认不输出 knowledge_cards；只有 needs_answer=true 且 question 很明确时才输出。
- 若同一问题在多条消息里连续追问，请合并成一张卡片。
- 不要把玩笑、闲聊、管理通知、单纯情绪表情提取为知识。
- 每批最多输出 6 张卡片，宁可少，不要为了凑数输出弱知识。

输出必须只包含 JSON，不要 markdown 代码块或其他文字。
```

</details>

<details>
<summary>默认 AI 预审核提示词</summary>

```text
你是游戏知识卡片的质量审核员。请判断这张卡片是否适合进入人工审核队列。

请把卡片分为三类：
1. approved=true：有可靠答案，适合进入待审核队列。
2. needs_answer=true：当前没有可靠答案，但 question 明确、可搜索、玩家后续值得补答。
3. approved=false 且 needs_answer=false：没价值、太含糊或不适合保留。

通过标准：
- question 是具体、可搜索、可被玩家自然提问的问题，不是话题名或上下文残片。
- answer 自包含、能直接回答 question，有实际信息量。
- 内容确实是游戏知识、玩法、机制、配置、报错、角色、装备、阵容、卡组、活动、版本、服务器、掉落、位置、推荐等。
- 不是广告、群通知、公开 token/接口/key/群号引流、账号交易、代练、充值推广、闲聊、情绪、玩笑或无关内容。
- 不把没有结论、猜测、互相矛盾的讨论包装成确定答案。

拒绝标准：
- 问答不相干，或问题和答案明显对不上。
- 缺上下文才能理解，例如“这个怎么弄”“那里有没有”“能打吗”且卡片没有补全对象。
- answer 只有“信息不足/不清楚/看情况/不强”等低信息量内容，且问题本身不值得后续补答。
- 包含公益 token、接口 key、通知群、广告、招募、外部引流、账号交易、敏感私密信息。

待回答标准：
- question 已经补全对象，玩家自然会搜索这个问题。
- 当前群聊没有可靠 answer，或 answer 明确表示“未提供/不清楚/需要进一步信息”。
- 这个问题属于游戏机制、配置、玩法、报错、角色、装备、阵容、卡组、活动、版本、服务器、推荐等，后续补答案有价值。

只输出 JSON，不要 markdown：
{
  "approved": true,
  "needs_answer": false,
  "question_worth_answering": false,
  "reason": "一句话说明",
  "score": 0.0,
  "issues": []
}
```

</details>

<details>
<summary>其他游戏可复制模板</summary>

```text
二游 / MMO / RPG 模板
你是【游戏名】玩家社群知识提取专家。重点识别角色养成、装备词条、技能机制、阵容配队、副本打法、活动兑换、资源规划、版本改动、服务器/区服差异。提取时保留角色名、装备名、技能名、活动名、boss 名、地图名和群内简称。不要把抽卡晒图、情绪吐槽、单纯战力攀比提取为知识。
```

```text
FPS / PVP / 竞技游戏模板
你是【游戏名】竞技社群知识提取专家。重点识别枪械/角色/英雄强度、地图点位、投掷物/技能释放、灵敏度/画面/按键设置、组队配合、排位机制、赛季改动、报错和网络问题。必须区分平台、服务器、赛季和版本，不要把战绩炫耀、开黑闲聊、情绪喷人提取为知识。
```

```text
生存 / 沙盒 / 服务器游戏模板
你是【游戏名】服务器知识提取专家。重点识别新手流程、资源获取、合成配方、建筑/机器/农场、怪物机制、地图位置、权限/指令/插件配置、服务器规则、版本或模组差异。必须保留服务器名、维度/地图、坐标、指令、配置项和群内俗称。不要把管理闲聊、招募广告、无关交易提取为知识。
```

```text
卡牌 / 策略 / 自走棋模板
你是【游戏名】策略知识提取专家。重点识别卡组构筑、阵容搭配、运营节奏、克制关系、关键牌/棋子/装备、版本环境、活动奖励、上分技巧。必须区分版本、赛季、模式和分段。不要把单局吐槽、纯晒欧非、无结论争论提取为知识。
```

</details>

## 完整配置说明

| 配置 | 默认值 | 说明 |
| --- | --- | --- |
| `plugin.enabled` | `true` | 是否启用插件 |
| `plugin.config_version` | `"1.0.2"` | 配置模板版本 |
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
├── config.example.toml
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

本项目使用 GPL-3.0-or-later。详见 [LICENSE](LICENSE)。

`kernel/` 目录保留上游许可与授权说明，详见 [kernel/LICENSE](kernel/LICENSE) 和 [kernel/LICENSE-MAIBOT-GPL.md](kernel/LICENSE-MAIBOT-GPL.md)。
