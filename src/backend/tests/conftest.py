import os
import sys
import tempfile
from pathlib import Path

# The test database and files live in a temporary folder: tests never touch the demo data.
os.environ["CLEARPATH_RUNTIME"] = tempfile.mkdtemp(prefix="clearpath_test_")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
