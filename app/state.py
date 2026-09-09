# -*- coding: utf-8 -*-
"""工作流状态：开关、下次时间、最近一次运行概览（data/state.json）。"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from .config import Settings

STATE_FILE_NAME = "state.json"


@dataclass
class LastRun:
    date: str = ""
    edition: str = ""
    status: str = ""          # ok | failed
    message: str = ""
    review_dir: str = ""
    finished_at: str = ""


@dataclass
class WorkflowState:
    auto_enabled: bool = False
    schedule_time: str = "09:00"
    last_run: LastRun = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.last_run is None:
            self.last_run = LastRun()


class StateStore:
    def __init__(self, settings: Settings):
        self.path: Path = settings.data_dir / STATE_FILE_NAME

    def read(self) -> WorkflowState:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            last = raw.get("last_run") or {}
            return WorkflowState(
                auto_enabled=bool(raw.get("auto_enabled", False)),
                schedule_time=str(raw.get("schedule_time", "09:00")),
                last_run=LastRun(**{k: last.get(k, "") for k in
                                    ("date", "edition", "status", "message", "review_dir", "finished_at")}),
            )
        except (FileNotFoundError, ValueError, TypeError):
            return WorkflowState()

    def write(self, state: WorkflowState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"auto_enabled": state.auto_enabled,
                        "schedule_time": state.schedule_time,
                        "last_run": asdict(state.last_run)},
                       ensure_ascii=False, indent=2),
            encoding="utf-8")

    # 便捷操作
    def get_auto(self) -> bool:
        return self.read().auto_enabled

    def set_auto(self, enabled: bool, schedule_time: str | None = None) -> WorkflowState:
        st = self.read()
        st.auto_enabled = enabled
        if schedule_time:
            st.schedule_time = schedule_time
        self.write(st)
        return st

    def record_last(self, date: str, edition: str, status: str, message: str, review_dir: str = "") -> None:
        st = self.read()
        st.last_run = LastRun(date=date, edition=edition, status=status, message=message,
                              review_dir=review_dir, finished_at=datetime.now().isoformat(timespec="seconds"))
        self.write(st)
