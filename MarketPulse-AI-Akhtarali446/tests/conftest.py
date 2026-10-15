"""Test configuration for Member 1 test suite.
Ensures the package root is on sys.path regardless of execution CWD.
"""
import sys
from pathlib import Path

package_root = Path(__file__).resolve().parent.parent
if str(package_root) not in sys.path:
    sys.path.insert(0, str(package_root))
