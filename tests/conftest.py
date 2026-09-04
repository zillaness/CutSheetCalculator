"""
file: conftest.py
version: 1.0
author: Sam Cao
created: 2026-09-04
last_updated: 2026-09-04
description: Puts the cut-sheet-builder scripts directory on sys.path for the test suite.
ai_update: Update last_updated and version. Append changelog at bottom.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "cut-sheet-builder", "scripts")
EXAMPLES = os.path.join(ROOT, "cut-sheet-builder", "assets", "examples")
sys.path.insert(0, SCRIPTS)

# CHANGELOG
# v1.0 (2026-09-04): Initial release.
