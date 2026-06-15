from __future__ import annotations

import argparse
import logging
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from .config import Settings
from .html_article import HTMLArticleProcessor
from .service import DraftPushService


LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="定时推送 HTML 到微信公众号草稿箱")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("check", help="检查本地配置和文件")

    push_parser = subparsers.add_parser("push", help="立即创建一篇草稿")
    push_parser.add_argument(
        "--refresh-cover",
        action="store_true",
        help="忽略封面素材缓存并重新上传",
    )
    subparsers.add_parser("schedule", help="按 PUSH_CRON 常驻运行")
    return parser


def check(settings: Settings) -> int:
    errors = settings.validation_errors()
    if settings.article_html.is_file():
        title = HTMLArticleProcessor.inspect_title(
            settings.article_html, settings.article_title
        )
        if not title:
            errors.append("缺少文章标题：设置 ARTICLE_TITLE 或 HTML <title>")
    try:
        ZoneInfo(settings.timezone)
        CronTrigger.from_crontab(settings.push_cron, timezone=settings.timezone)
    except (ValueError, ZoneInfoNotFoundError) as exc:
        errors.append(f"定时配置无效: {exc}")

    if errors:
        for error in errors:
            LOGGER.error(error)
        return 1
    LOGGER.info("配置检查通过")
    return 0


def push_once(settings: Settings, refresh_cover: bool = False) -> None:
    media_id = DraftPushService(settings).push(refresh_cover=refresh_cover)
    LOGGER.info("草稿创建成功，media_id=%s", media_id)


def run_scheduler(settings: Settings) -> int:
    if check(settings) != 0:
        return 1
    scheduler = BlockingScheduler(timezone=settings.timezone)
    trigger = CronTrigger.from_crontab(
        settings.push_cron, timezone=settings.timezone
    )
    scheduler.add_job(
        push_once,
        trigger=trigger,
        args=[settings],
        id="wechat-draft-push",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )
    LOGGER.info(
        "定时器已启动：cron=%s，timezone=%s；按 Ctrl+C 停止",
        settings.push_cron,
        settings.timezone,
    )
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        LOGGER.info("定时器已停止")
    return 0


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )
    args = build_parser().parse_args()
    settings = Settings.load()
    try:
        if args.command == "check":
            return check(settings)
        if args.command == "push":
            push_once(settings, refresh_cover=args.refresh_cover)
            return 0
        if args.command == "schedule":
            return run_scheduler(settings)
    except Exception:
        LOGGER.exception("执行失败")
        return 1
    return 1

