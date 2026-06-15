from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from wechat_draft_pusher.config import Settings
from wechat_draft_pusher.html_article import HTMLArticleProcessor
from wechat_draft_pusher.service import DraftPushService


class FakeAPI:
    def __init__(self) -> None:
        self.cover_uploads = 0

    def upload_content_image(
        self, content: bytes, filename: str, content_type: str | None = None
    ) -> str:
        return f"https://mmbiz.qpic.cn/{filename}"

    def upload_permanent_thumb(self, image_path: Path) -> str:
        self.cover_uploads += 1
        return "cached-thumb-media-id"


class HTMLArticleProcessorTests(unittest.TestCase):
    def test_reads_title_and_body(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            html_path = Path(directory) / "article.html"
            html_path.write_text(
                "<html><head><title>测试标题</title></head>"
                "<body><p>正文</p><script>alert(1)</script></body></html>",
                encoding="utf-8",
            )

            article = HTMLArticleProcessor(FakeAPI()).process(html_path)

            self.assertEqual(article.title, "测试标题")
            self.assertIn("<p>正文</p>", article.content)
            self.assertNotIn("script", article.content)


class CoverCacheTests(unittest.TestCase):
    def test_reuses_cover_for_same_account_and_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            html_path = root / "article.html"
            cover_path = root / "cover.jpg"
            html_path.write_text("<title>标题</title><p>正文</p>", encoding="utf-8")
            cover_path.write_bytes(b"fake-jpeg-for-cache-test")
            settings = Settings(
                app_id="wx-test",
                app_secret="secret",
                article_html=html_path,
                cover_image=cover_path,
                article_title="",
                article_author="",
                article_digest="",
                article_source_url="",
                need_open_comment=False,
                only_fans_can_comment=False,
                push_cron="0 9 * * 1",
                timezone="Asia/Shanghai",
                cache_dir=root / ".cache",
            )
            service = DraftPushService(settings)
            fake_api = FakeAPI()
            service.api = fake_api

            first = service._get_cover_media_id(refresh=False)
            second = service._get_cover_media_id(refresh=False)

            self.assertEqual(first, second)
            self.assertEqual(fake_api.cover_uploads, 1)


if __name__ == "__main__":
    unittest.main()
