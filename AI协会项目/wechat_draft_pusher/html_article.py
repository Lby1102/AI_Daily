from __future__ import annotations

import base64
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests
from bs4 import BeautifulSoup

from .wechat_api import WeChatAPI


@dataclass(frozen=True)
class ParsedArticle:
    title: str
    content: str
    uploaded_image_count: int


class HTMLArticleProcessor:
    def __init__(self, api: WeChatAPI, timeout: int = 30) -> None:
        self.api = api
        self.timeout = timeout

    def process(self, html_path: Path, configured_title: str = "") -> ParsedArticle:
        soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")
        title = configured_title or self._metadata_title(soup)
        if not title:
            raise ValueError("缺少文章标题：请设置 ARTICLE_TITLE 或 HTML <title>")

        uploaded = 0
        for index, image in enumerate(soup.find_all("img"), start=1):
            source = (image.get("src") or "").strip()
            if not source or self._is_wechat_hosted(source):
                continue
            content, filename, content_type = self._load_image(
                source, html_path.parent, index
            )
            image["src"] = self.api.upload_content_image(
                content, filename, content_type
            )
            uploaded += 1

        for tag in soup.find_all(["script", "noscript"]):
            tag.decompose()

        container = soup.body if soup.body else soup
        content = "".join(str(child) for child in container.contents).strip()
        if not content:
            raise ValueError("HTML 正文为空")
        return ParsedArticle(title=title, content=content, uploaded_image_count=uploaded)

    @staticmethod
    def inspect_title(html_path: Path, configured_title: str = "") -> str:
        soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")
        return configured_title or HTMLArticleProcessor._metadata_title(soup)

    @staticmethod
    def _metadata_title(soup: BeautifulSoup) -> str:
        meta = soup.find("meta", attrs={"name": "wechat:title"})
        if meta and meta.get("content"):
            return str(meta["content"]).strip()
        if soup.title and soup.title.string:
            return soup.title.string.strip()
        heading = soup.find("h1")
        return heading.get_text(" ", strip=True) if heading else ""

    def _load_image(
        self, source: str, base_dir: Path, index: int
    ) -> tuple[bytes, str, str]:
        if source.startswith("data:"):
            return self._decode_data_uri(source, index)

        parsed = urlparse(source)
        if parsed.scheme in {"http", "https"}:
            response = requests.get(source, timeout=self.timeout)
            response.raise_for_status()
            filename = Path(unquote(parsed.path)).name or f"remote-{index}.jpg"
            content_type = response.headers.get("Content-Type", "").split(";")[0]
            return response.content, filename, content_type or "image/jpeg"

        if parsed.scheme == "file":
            image_path = Path(unquote(parsed.path.lstrip("/")))
        else:
            image_path = base_dir / unquote(parsed.path)
        image_path = image_path.resolve()
        if not image_path.is_file():
            raise FileNotFoundError(f"正文图片不存在: {image_path}")
        content_type = mimetypes.guess_type(image_path.name)[0] or "image/jpeg"
        return image_path.read_bytes(), image_path.name, content_type

    @staticmethod
    def _decode_data_uri(source: str, index: int) -> tuple[bytes, str, str]:
        header, encoded = source.split(",", 1)
        if ";base64" not in header:
            raise ValueError("仅支持 base64 格式的 data URI 图片")
        content_type = header[5:].split(";")[0] or "image/png"
        extension = mimetypes.guess_extension(content_type) or ".png"
        return base64.b64decode(encoded), f"embedded-{index}{extension}", content_type

    @staticmethod
    def _is_wechat_hosted(source: str) -> bool:
        hostname = (urlparse(source).hostname or "").lower()
        return hostname.endswith(".qpic.cn") or hostname.endswith(".weixin.qq.com")

