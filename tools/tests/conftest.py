"""conftest for tools/tests/ - add tools/ to sys.path so `from manifest_utils import ...` works."""
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))
