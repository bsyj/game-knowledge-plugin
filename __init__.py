"""GameKnowledge plugin package."""

import sys
from pathlib import Path

# Ensure the plugin root is on sys.path so that kernel modules
# can use absolute imports like `from gk_shims.logger_shim import ...`
# regardless of how MaiBot mounts the plugin package.
_PKG_ROOT = Path(__file__).resolve().parent
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))
