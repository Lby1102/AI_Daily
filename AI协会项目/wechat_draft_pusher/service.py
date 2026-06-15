from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from .config import Settings
from .html_article import HTMLArticleProcessor
from .wechat_api import WeChatAPI


LOGGER = logging.getLogger(__name__)


class DraftPushService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.api = WeChatAPI(settings.app_id, settings.app_secret)

    def push(self, refresh_cover: bool = False) -> str:
        errors = self.settings.validation_errors()
        if errors:
            raise ValueError("；".join(errors))

        LOGGER.info("正在处理 HTML 和正文图片: %s", self.settings.article_html)
        parsed = HTMLArticleProcessor(self.api).process(
            self.settings.article_html, self.settings.article_title
        )
        LOGGER.info("正文处理完成，上传了 %d 张图片", parsed.uploaded_image_count)

        thumb_media_id = self._get_cover_media_id(refresh_cover)
        article: dict[str, Any] = {
            "title": parsed.title,
            "author": self.settings.article_author,
            "digest": self.settings.article_digest,
            "content": parsed.content,
            "content_source_url": self.settings.article_source_url,
            "thumb_media_id": thumb_media_id,
            "need_open_comment": int(self.settings.need_open_comment),
            "only_fans_can_comment": int(self.settings.only_fans_can_comment),
        }
        LOGGER.info("正在创建公众号草稿: %s", parsed.title)
        return self.api.add_draft(article)

    def _get_cover_media_id(self, refresh: bool) -> str:
        digest = self._sha256(self.settings.cover_image)
        cache_file = self.settings.cache_dir / "cover-media.json"

        if not refresh:
            cached = self._read_cache(cache_file)
            if (
                cached.get("app_id") == self.settings.app_id
                and cached.get("sha256") == digest
                and cached.get("media_id")
            ):
                LOGGER.info("复用已缓存的封面素材")
                return str(cached["media_id"])

        LOGGER.info("正在上传封面永久素材: %s", self.settings.cover_image)
        media_id = self.api.upload_permanent_thumb(self.settings.cover_image)
        self.settings.cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(
            json.dumps(
                {
                    "app_id": self.settings.app_id,
                    "sha256": digest,
                    "media_id": media_id,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return media_id

    @staticmethod
    def _sha256(path: Path) -> str:
        hasher = hashlib.sha256()
        with path.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    @staticmethod
    def _read_cache(path: Path) -> dict[str, Any]:
        if not path.is_file():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

