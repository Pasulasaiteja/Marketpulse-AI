"""Test configuration for Member 4 / LLM test suite.
Ensures the submodule package root is on sys.path regardless of execution CWD,
and isolates its mocks package from colliding with other submodules.
"""
import sys
from pathlib import Path

package_root = Path(__file__).resolve().parent.parent
if str(package_root) not in sys.path:
    sys.path.insert(0, str(package_root))
else:
    sys.path.remove(str(package_root))
    sys.path.insert(0, str(package_root))

for mod in list(sys.modules.keys()):
    if mod == "mocks" or mod.startswith("mocks."):
        del sys.modules[mod]
