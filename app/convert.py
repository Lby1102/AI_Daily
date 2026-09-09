# -*- coding: utf-8 -*-
"""模块 1（crawler JSON）→ 模块 2~4（raw txt）转换。

只取文字信息（标题/摘要/来源/链接/时间/热度），不包含任何图片内容；
图片在选文后由 images 模块单独抓取。模块 2~4 不做确定性解析，整文交模型，
因此这里输出易读、信息完整的分条块即可。
"""
from __future__ import annotations

import json
from pathlib import Path

SEP = "---"


def load_crawl_items(json_path: Path, top: int = 200) -> list[dict]:
    data = json.loads(json_path.read_text(encoding="utf-8"))
    items = data.get("items") or []
    return items[:top]


def _heat_text(item: dict) -> str:
    parts = []
    sc = item.get("source_count")
    if sc:
        parts.append(f"跨来源 {sc} 家")
    rank = item.get("best_rank")
    if rank not in (None, 999, 0):
        parts.append(f"榜单最高第 {rank} 名")
    rel = item.get("relevance_score")
    if rel is not None:
        parts.append(f"相关性 {rel}/100")
    return "，".join(parts) if parts else "无"


def _source_names(item: dict) -> str:
    names = [s.get("source_name", "") for s in (item.get("sources") or []) if s.get("source_name")]
    seen, out = set(), []
    for n in names:
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return "、".join(out[:4]) or "未知"


def format_items_txt(items: list[dict]) -> str:
    blocks: list[str] = []
    for i, item in enumerate(items, 1):
        title = (item.get("title") or "").strip()
        if not title:
            continue
        body = (item.get("snippet") or "").strip()
        url = (item.get("url") or "").strip()
        lines = [f"标题：{title}", ""]
        if body:
            lines += ["正文：", body, ""]
        lines += [f"来源：{_source_names(item)}",
                  f"发布时间：{item.get('latest_published_at') or item.get('published_at') or '未知'}",
                  f"原文链接：{url}",
                  f"热度：{_heat_text(item)}"]
        blocks.append("\n".join(lines))
    return "\n\n" + f"\n{SEP}\n\n".join(blocks) + "\n"


def build_raw_txt(json_path: Path, out_txt: Path, top: int = 200) -> Path:
    """读爬虫 JSON，写模块 2~4 的 raw_news.txt，返回写入路径。"""
    items = load_crawl_items(json_path, top=top)
    if not items:
        raise ValueError(f"爬虫输出没有可用条目：{json_path}")
    header = (f"AI 每日资讯原始材料（{len(items)} 条候选，按爬虫去重后顺序排列）。\n"
              f"请从以下候选中筛选与 AI 最相关、可信且热门的资讯。\n\n")
    out_txt.parent.mkdir(parents=True, exist_ok=True)
    out_txt.write_text(header + format_items_txt(items), encoding="utf-8")
    return out_txt
