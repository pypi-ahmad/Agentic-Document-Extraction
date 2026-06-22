"""Repo-root conftest for pytest.

Adds the ``scripts/`` directory to ``sys.path`` so tests in
``backend/tests/`` can import modules like ``scripts.fetch_docvqa``.
The ``scripts/`` directory is not a Python package (no
``__init__.py``) and lives at the repo root, outside pytest's
default test root.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
SCRIPTS_DIR = REPO_ROOT / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
