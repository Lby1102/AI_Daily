# -*- coding: utf-8 -*-
"""每日自动生成：开启后每天到达 schedule_time 自动执行一次 run_today。

不阻塞审核/推送：自动只负责「生成」，推送永远等人工审核后执行。
"""
from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

from . import orchestrator as orch
from .config import Settings


def _auto_last_file(s: Settings) -> Path:
    return s.data_dir / "auto_last_date.txt"


def _should_run(s: Settings) -> tuple[bool, str]:
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    try:
        hh, mm = (s.schedule_time or "09:00").strip().split(":")
        target = int(hh) * 60 + int(mm)
    except (ValueError, TypeError):
        return False, f"schedule_time 格式错误：{s.schedule_time!r}"
    current = now.hour * 60 + now.minute
    last = ""
    if _auto_last_file(s).exists():
        last = _auto_last_file(s).read_text(encoding="utf-8").strip()
    if current >= target and last != today:
        return True, today
    return False, ""


def serve(settings: Settings | None = None) -> None:
    s = settings or Settings()
    orch_ = orch.Orchestrator(s)
    print(f"自动生成服务已启动（当前开关={s.auto_enabled}，时间={s.schedule_time}，Ctrl+C 退出）")
    try:
        while True:
            if s.auto_enabled:
                go, today = _should_run(s)
                if go:
                    print(f"[{datetime.now():%H:%M:%S}] 到达计划时间，开始今日生成…")
                    try:
                        m = orch_.run_today()
                        print("今日生成完成：", m["review_dir"])
                        _auto_last_file(s).write_text(today, encoding="utf-8")
                    except Exception as exc:  # noqa: BLE001
                        print("今日生成失败：", exc)
            time.sleep(20)
    except KeyboardInterrupt:
        print("\n服务已停止")
