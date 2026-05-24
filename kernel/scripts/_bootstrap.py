from __future__ import annotations

import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
KERNEL_ROOT = CURRENT_DIR.parent  # kernel/
PLUGIN_ROOT = KERNEL_ROOT.parent  # game-knowledge-plugin/
WORKSPACE_ROOT = PLUGIN_ROOT.parent  # MaiM-with-u/

for _path in (KERNEL_ROOT, PLUGIN_ROOT):
    _path_str = str(_path)
    if _path_str not in sys.path:
        sys.path.insert(0, _path_str)

from kernel.paths import config_path, default_data_dir, resolve_repo_path

DEFAULT_CONFIG_PATH = config_path()
DEFAULT_DATA_DIR = default_data_dir()
DEFAULT_DB_PATH = PLUGIN_ROOT / "data" / "MaiBot.db"
