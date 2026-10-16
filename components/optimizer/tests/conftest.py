"""Test configuration for Member 3 (Optimizer) test suite.
Ensures the submodule package root is on sys.path regardless of execution CWD,
and isolates Member 3's mocks module from colliding with other submodules.
"""
import sys
from pathlib import Path

package_root = Path(__file__).resolve().parent.parent
if str(package_root) not in sys.path:
    sys.path.insert(0, str(package_root))
else:
    # Move to the front so Member 3's own packages (optimizer, mocks) take priority
    sys.path.remove(str(package_root))
    sys.path.insert(0, str(package_root))

for mod in list(sys.modules.keys()):
    if mod == "mocks" or mod.startswith("mocks."):
        del sys.modules[mod]
