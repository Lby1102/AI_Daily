from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path
from string import Template
from urllib.parse import urlparse

from .schema import Article


def _safe_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"不合法的来源链接：{value!r}")
    return escape(value, quote=True)


def render_article(article: Article, template_path: Path) -> str:
    template = Template(template_path.read_text(encoding="utf-8"))
    item_blocks: list[str] = []
    for index, item in enumerate(article.items, start=1):
        paragraphs = "\n".join(f"<p>{escape(paragraph)}</p>" for paragraph in item.paragraphs)
        item_blocks.append(
            f"""
            <article class="feature-article">
              <p class="section-label">精选文章 {index:02d}</p>
              <h2>{escape(item.title)}</h2>
              <p class="article-lead">{escape(item.lead)}</p>
              <div class="article-body">
                {paragraphs}
              </div>
              <p class="source">原文来源：<a href="{_safe_url(item.source_url)}" target="_blank" rel="noopener noreferrer">{escape(item.source_name)}</a></p>
            </article>
            """.strip()
        )

    return template.safe_substitute(
        title=escape(article.title),
        introduction=escape(article.introduction),
        conclusion=escape(article.conclusion),
        generated_at=escape(datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")),
        news_items="\n".join(item_blocks),
    )
