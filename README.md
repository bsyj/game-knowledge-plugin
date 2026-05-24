# GameKnowledge Plugin for MaiBot

Industrial-grade game knowledge analysis, storage, graph, and retrieval plugin for [MaiBot](https://github.com/MaiM-with-u/MaiBot).

## Features

- **Game Knowledge Extraction** — Automatically analyzes group chat messages to extract game knowledge
- **AI-Powered Review** — AI-assisted pre-review for knowledge quality
- **Vector Search** — FAISS-powered semantic search for game knowledge
- **Graph Relations** — Builds knowledge graphs from extracted relations
- **Episode Memory** — Long-term episodic memory retrieval
- **Independent WebUI** — Built-in management interface for knowledge review, maintenance, and statistics
- **Board & Announcements** — Bulletin board and announcement system for game communities

## Installation

```bash
# 1. Clone into your MaiBot plugins directory
cd MaiBot/plugins/
git clone https://github.com/bsyj/game-knowledge-plugin.git

# 2. Install Python dependencies
pip install -r game-knowledge-plugin/requirements.txt

# 3. Enable the plugin in config.toml or via WebUI
```

## Requirements

- Python 3.10+
- MaiBot v1.0.0+
- pip packages: numpy, scipy, networkx, pyarrow, pandas, faiss-cpu, fastapi, uvicorn, nest-asyncio, jieba, rich, tenacity

## Configuration

Edit `config.toml` in the plugin directory:

- `plugin.enabled` — Enable/disable the plugin
- `storage.data_dir` — Data storage directory
- `web.enabled` — Enable independent WebUI (default: `http://127.0.0.1:5810`)
- `collector.enabled` — Enable auto message collection from group chats
- `collector.allowed_source_group_ids` — Whitelist of group IDs for collection
- `episode.enabled` — Enable episode memory

## WebUI

When enabled, access the management interface at `http://127.0.0.1:5810`.

To rebuild the WebUI frontend:
```bash
cd webui/
npm install
npm run build
```

## Commands

| Command | Description |
|---------|-------------|
| `/gkb status` | Show plugin status |
| `/gkb search <query>` | Search game knowledge |
| `/gkb review` | Review pending knowledge entries |

## License

GPL-3.0-or-later
