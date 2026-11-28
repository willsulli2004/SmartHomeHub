"""Lets pytest import alarm_analytics (and the mock robot) when run from the repo folder."""

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
# The end-to-end test runs the mock robot against the service.
sys.path.insert(0, str(HERE.parent.parent / "tools" / "mock-robot"))
