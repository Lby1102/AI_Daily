from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.wechat_web import prepare_article


class PrepareArticleTests(unittest.TestCase):
    def test_extracts_unicode_and_local_images_without_escape_sequences(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "pic.jpg").write_bytes(b"jpeg")
            article = root / "article.html"
            article.write_text(
                '<html><head><meta name="wechat:title" content="中文标题"></head>'
                '<body><main><h1>中文标题</h1><p class="introduction">中文摘要</p>'
                '<h2>小标题</h2><img src="pic.jpg"><p>正文</p></main></body></html>',
                encoding="utf-8",
            )
            result = prepare_article(article)
            self.assertEqual(result.title, "中文标题")
            self.assertEqual(result.digest, "中文摘要")
            self.assertIn("中文摘要", result.html)
            self.assertNotIn("\\u", result.html)
            self.assertNotIn("<h1", result.html)
            self.assertEqual(result.images[0][1], (root / "pic.jpg").resolve())
            self.assertIn(result.images[0][0], result.html)


if __name__ == "__main__":
    unittest.main()
