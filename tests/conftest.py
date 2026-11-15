import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _harness  # noqa: E402

_harness.install_stubs()
sys.path.insert(0, str(_harness.INCLUDES))  # campus_config, frontend_branding
