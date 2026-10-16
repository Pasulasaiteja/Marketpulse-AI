"""
Pytest configuration for MarketPulse AI - Demand Forecasting & Market Signals.
Ensures project root is automatically in sys.path for test execution.
"""
import sys
from pathlib import Path

# Add project root directory to sys.path so modules import reliably
ROOT_DIR = Path(__file__).parent.resolve()
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
