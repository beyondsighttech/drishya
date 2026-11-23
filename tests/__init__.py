"""Test pure components without importing NVDA's plugin entry point."""
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
package = types.ModuleType("drishya")
package.__path__ = [str(ROOT / "addon" / "globalPlugins" / "drishya")]
sys.modules.setdefault("drishya", package)
