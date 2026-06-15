from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _path_from_env(name: str, default: str) -> Path:
    value = os.getenv(name, default).strip()
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def _bool_from_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_id: str
    app_secret: str
    article_html: Path
    cover_image: Path
    article_title: str
    article_author: str
    article_digest: str
    article_source_url: str
    need_open_comment: bool
    only_fans_can_comment: bool
    push_cron: str
    timezone: str
    cache_dir: Path

    @classmethod
    def load(cls) -> "Settings":
        load_dotenv(PROJECT_ROOT / ".env")
        return cls(
            app_id=os.getenv("WECHAT_APP_ID", "").strip(),
            app_secret=os.getenv("WECHAT_APP_SECRET", "").strip(),
            article_html=_path_from_env("ARTICLE_HTML", "content/article.html"),
            cover_image=_path_from_env("COVER_IMAGE", "content/test.png"),
            article_title=os.getenv("ARTICLE_TITLE", "").strip(),
            article_author=os.getenv("ARTICLE_AUTHOR", "").strip(),
            article_digest=os.getenv("ARTICLE_DIGEST", "").strip(),
            article_source_url=os.getenv("ARTICLE_SOURCE_URL", "").strip(),
            need_open_comment=_bool_from_env("NEED_OPEN_COMMENT"),
            only_fans_can_comment=_bool_from_env("ONLY_FANS_CAN_COMMENT"),
            push_cron=os.getenv("PUSH_CRON", "0 9 * * 1").strip(),
            timezone=os.getenv("TIMEZONE", "Asia/Shanghai").strip(),
            cache_dir=PROJECT_ROOT / ".cache",
        )

    def validation_errors(self, require_credentials: bool = True) -> list[str]:
        errors: list[str] = []
        if require_credentials and not self.app_id:
            errors.append("缺少 WECHAT_APP_ID")
        if require_credentials and not self.app_secret:
            errors.append("缺少 WECHAT_APP_SECRET")
        if not self.article_html.is_file():
            errors.append(f"HTML 文件不存在: {self.article_html}")
        if not self.cover_image.is_file():
            errors.append(f"封面图片不存在: {self.cover_image}")
        elif self.cover_image.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
            errors.append("封面图片应为 JPG 或 PNG")
        if not self.push_cron:
            errors.append("PUSH_CRON 不能为空")
        if not self.timezone:
            errors.append("TIMEZONE 不能为空")
        return errors

