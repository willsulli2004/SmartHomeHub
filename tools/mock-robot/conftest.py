"""Lets pytest import mock_robot when run from the repo folder."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
