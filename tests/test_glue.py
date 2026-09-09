# -*- coding: utf-8 -*-
"""胶水层离线单测（不联网、不调 LLM）。

运行：python -m unittest discover -s tests -v
"""
from __future__ import annotations

import io
import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "modules" / "summarize" / "src"))

from PIL import Image  # noqa: E402

from app import convert, docx_builder, html_wechat, images  # noqa: E402
from app.config import ROOT  # noqa: E402

SAMPLE = ROOT / "data" / "sample" / "sample_items.json"
SRC_HTML = ROOT / "tests" / "fixtures" / "article.html"
_TEST_ROOT = ROOT / "data" / ".test-tmp"


def _tmp() -> Path:
    """工作区内的临时目录（避免沙箱对系统 TEMP chmod 的限制）。"""
    p = _TEST_ROOT / uuid.uuid4().hex[:12]
    p.mkdir(parents=True, exist_ok=True)
    return p


def _make_jpeg_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (320, 180), (60, 120, 200)).save(buf, format="JPEG")
    return buf.getvalue()


class ConvertTest(unittest.TestCase):
    def test_sample_to_txt(self):
        out = convert.build_raw_txt(SAMPLE, _tmp() / "raw.txt")
        txt = out.read_text(encoding="utf-8")
        self.assertIn("标题：", txt)
        self.assertIn("原文链接：https://example.com", txt)
        self.assertIn("热度：", txt)

    def test_missing_items_raises(self):
        bad = _tmp() / "empty.json"
        bad.write_text('{"items": []}', encoding="utf-8")
        with self.assertRaises(ValueError):
            convert.build_raw_txt(bad, bad.parent / "raw.txt")


class ImageTest(unittest.TestCase):
    def test_slugify(self):
        self.assertEqual(images.slugify("DM-R2 发布！重磅"), "dm-r2-发布-重磅")
        self.assertTrue(len(images.slugify("x" * 100)) <= 24)

    def test_normalize_jpeg(self):
        out = _tmp() / "a.jpg"
        self.assertTrue(images.normalize_jpeg(_make_jpeg_bytes(), out))
        with Image.open(out) as im:
            self.assertEqual(im.format, "JPEG")
            self.assertLessEqual(max(im.size), 1400)

    def test_discover_pattern(self):
        # 只测 URL 提取正则路径（不联网）：monkeypatch 掉网络函数
        def fake_get(url, timeout=0.0):
            class R:
                status_code = 200
                headers = {"Content-Type": "text/html"}
                text = ('<meta property="og:image" content="https://x.com/a.png">'
                        '<img src="https://x.com/b.jpg"><img src="/c.gif">'
                        '<img src="data:image/png;base64,xx"><img src="//cdn/x.png">')
            return R()

        class FakeSession:
            def get(self, url, timeout=0.0):  # noqa: ARG002
                return fake_get(url, timeout)

            def mount(self, *a):  # noqa: ARG002
                pass
            headers = {}

        old = images._SESSION
        images._SESSION = FakeSession()
        try:
            got = images.discover_images("https://example.com/news", timeout=3)
        finally:
            images._SESSION = old
        self.assertEqual(got[0], "https://x.com/a.png")
        self.assertIn("https://x.com/b.jpg", got)
        self.assertTrue(all(u.startswith("http") for u in got))

    def test_visual_duplicate_images_are_skipped(self):
        first = io.BytesIO()
        second = io.BytesIO()
        image = Image.new("RGB", (320, 180), (60, 120, 200))
        image.save(first, format="JPEG", quality=70)
        image.save(second, format="JPEG", quality=95)
        with patch.object(images, "download_image",
                          side_effect=[first.getvalue(), second.getvalue()]):
            saved = images._save_from_urls(
                ["https://example.com/a.jpg", "https://example.com/b.jpg"],
                _tmp(), 2, 1,
            )
        self.assertEqual(len(saved), 1)


class HtmlDocxTest(unittest.TestCase):
    def test_wechat_html_and_docx_with_images(self):
        tmp = _tmp()
        att = tmp / "attachments" / "01-dm-r2"
        att.mkdir(parents=True)
        (att / "01.jpg").write_bytes(_make_jpeg_bytes())
        img_map = {1: [att / "01.jpg"]}

        final = html_wechat.build_wechat_html(SRC_HTML, tmp / "article.html", img_map)
        html_txt = final.read_text(encoding="utf-8")
        self.assertIn("wechat:title", html_txt)
        self.assertIn("<img", html_txt)
        self.assertIn("attachments/01-dm-r2/01.jpg", html_txt)

        docx_path = docx_builder.build_docx(final, tmp / "n.docx")
        self.assertTrue(docx_path.exists())
        # docx 有正文且内嵌了图片
        import zipfile
        with zipfile.ZipFile(docx_path) as z:
            self.assertTrue(any(n.startswith("word/media/") for n in z.namelist()))

    def test_wechat_html_meta_not_duplicated(self):
        tmp = _tmp()
        f1 = html_wechat.build_wechat_html(SRC_HTML, tmp / "a.html", {})
        f2 = html_wechat.build_wechat_html(f1, tmp / "b.html", {})
        self.assertEqual(f2.read_text(encoding="utf-8").count("wechat:title"), 1)


if __name__ == "__main__":
    unittest.main()
