# -*- coding: utf-8 -*-
"""Print the review dir of the latest successful run (for 2-打开审核文件夹.bat)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import state as state_mod
from app.config import Settings

store = state_mod.StateStore(Settings())
last = store.read().last_run
candidate = Path(last.review_dir) if last and last.review_dir else None
if candidate and candidate.exists():
    print(candidate)
else:
    print(Settings().review_dir)
