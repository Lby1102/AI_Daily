# -*- coding: utf-8 -*-
"""把模块 2~4 生成的 article.html 增强为可推送给公众号的版本：
1) 补 <meta name="wechat:title">（标题取自 <title>/<h1>）；
2) 在每篇精选文章的导语后插入本地配图 <img>（相对本文件目录的路径，
   模块 6 会上传并把 src 换成微信地址）。
"""
from __future__ import annotations

from pathlib import Path

from bs4 import BeautifulSoup


def build_wechat_html(source_html: Path, dest_html: Path,
                      images: dict[int, list[Path]], title: str = "") -> Path:
    soup = BeautifulSoup(source_html.read_text(encoding="utf-8"), "html.parser")
    if not title:
        tag = soup.find("meta", attrs={"name": "wechat:title"})
        if tag and tag.get("content"):
            title = tag["content"].strip()
        elif soup.title and soup.title.string:
            title = soup.title.string.strip()
        else:
            h1 = soup.find("h1")
            title = (h1.get_text(" ", strip=True) if h1 else "") or "AI 资讯"

    # 1) meta 标题（只插一次）
    if not soup.find("meta", attrs={"name": "wechat:title"}):
        meta = soup.new_tag("meta")
        meta["name"] = "wechat:title"
        meta["content"] = title
        head = soup.head or soup
        head.insert(0, meta)

    # 2) 每篇配图（按 .feature-article 出现顺序匹配 images 序号）
    dest_html.parent.mkdir(parents=True, exist_ok=True)
    rel_base = dest_html.parent
    articles = soup.select("article.feature-article")
    for idx, article in enumerate(articles, 1):
        files = images.get(idx) or []
        if not files:
            continue
        anchor = article.select_one(".article-lead")
        if anchor is None:
            anchor = article.select_one(".article-body")
        node = anchor
        for file_path in files[:2]:  # 公众号版每篇最多插 2 张，其余留在附件
            rel = Path("attachments") / file_path.parent.name / file_path.name
            img_tag = soup.new_tag("img")
            img_tag["src"] = rel.as_posix()
            img_tag["style"] = "max-width:100%;border-radius:8px;margin:6px 0 18px;display:block;"
            node.insert_after(img_tag)
            node = img_tag

    dest_html.write_text(str(soup), encoding="utf-8")
    return dest_html
