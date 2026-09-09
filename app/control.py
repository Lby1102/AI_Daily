# -*- coding: utf-8 -*-
"""统一控制入口（本次为命令行交互版；后续前端按钮直接调用相同函数）。

用法（在 AI-Daily-Workflow/ 根目录执行）：
  python app/control.py today              # 开始今日新闻生成（真实爬取）
  python app/control.py today --sample     # 用内置样例数据联调（不联网）
  python app/control.py status             # 查看开关与上次运行
  python app/control.py auto on            # 开启每日自动生成
  python app/control.py auto off
  python app/control.py auto on --time 08:30
  python app/control.py push [--date 2026-09-03]   # 审核完毕 → 推送微信草稿箱
  python app/control.py serve              # 常驻自动调度服务
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 允许从 AI-Daily-Workflow/ 根目录直接执行：python app/control.py ...
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import orchestrator as orch  # noqa: E402
from app import scheduler as sched  # noqa: E402
from app import state as state_mod  # noqa: E402
from app.config import Settings  # noqa: E402
from app.review_picker import choose_article  # noqa: E402
from app.wechat_web import push as push_wechat_web  # noqa: E402


def _add_date_arg(p: argparse.ArgumentParser) -> None:
    p.add_argument("--date", default="", help="YYYY-MM-DD（默认取最近一次运行日期）")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="control", description="AI Daily Workflow 控制台")
    sub = parser.add_subparsers(dest="command", required=True)

    p_today = sub.add_parser("today", help="开始今日新闻生成")
    _add_date_arg(p_today)
    p_today.add_argument("--sample", action="store_true", help="使用内置样例数据（不爬取）")
    p_today.add_argument("--no-images", action="store_true", help="跳过配图抓取")
    p_today.add_argument("--feedback", default="", help="人工反馈文件路径（审核不通过时）")

    sub.add_parser("status", help="查看状态")
    sub.add_parser("serve", help="启动每日自动生成服务（常驻）")

    p_auto = sub.add_parser("auto", help="开启/关闭每日自动生成")
    p_auto.add_argument("state", choices=["on", "off"])
    p_auto.add_argument("--time", default="", help="如 08:30")

    p_push = sub.add_parser("push", help="选择 review 中的 HTML 稿件并上传草稿箱")
    push_target = p_push.add_mutually_exclusive_group()
    push_target.add_argument("--date", default="", help="指定 review 子目录，不指定则交互选择")
    push_target.add_argument("--file", default="", help="指定 review 内的 HTML 文件路径")

    args = parser.parse_args(argv)
    s = Settings()
    store = state_mod.StateStore(s)

    try:
        if args.command == "today":
            o = orch.Orchestrator(s)
            m = o.run_today(args.date or None, use_sample=args.sample,
                            fetch_images=not args.no_images,
                            feedback=Path(args.feedback) if args.feedback else None)
            print("今日生成完成：")
            print("  审核文件夹:", m["review_dir"])
            print("  Word 新闻稿:", m["docx"])
            print("  公众号 HTML:", m["article_html"])
            print("  入选文章数:", m["news_count"], "| 配图组数:", len(m["image_groups"]))
            return 0

        if args.command == "status":
            st = store.read()
            print("自动生成:", "开" if st.auto_enabled else "关", "| 时间:", st.schedule_time)
            last = st.last_run
            if last and last.date:
                print(f"上次运行: {last.date} [{last.status}] {last.message} | {last.finished_at}")
                if last.review_dir:
                    print("  审核目录:", last.review_dir)
            else:
                print("尚未运行过 today")
            return 0

        if args.command == "auto":
            enabled = args.state == "on"
            st = store.set_auto(enabled, args.time or None)
            print("自动生成已", "开启" if st.auto_enabled else "关闭",
                  "| 时间:", st.schedule_time, "（运行 serve 或常驻本进程生效）")
            return 0

        if args.command == "push":
            article = Path(args.file) if args.file else None
            if not args.date and article is None:
                article = choose_article(s.review_dir)
                if article is None:
                    print("已取消上传。")
                    return 0
            if article is None:
                folder = s.review_dir / args.date
                article = folder / "article.html"
                if not article.is_file():
                    raise orch.OrchestratorError(f"找不到稿件：{article}")
            title = push_wechat_web(article)
            print("已上传草稿：", title)
            print("可在公众号后台草稿箱查看预览。")
            return 0

        if args.command == "serve":
            sched.serve(s)
            return 0
    except orch.OrchestratorError as exc:
        print(f"运行失败：{exc}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(f"运行失败：{exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n已取消")
        return 130
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
