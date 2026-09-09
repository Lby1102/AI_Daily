#!/usr/bin/env python3
"""Optional downstream helper: convert collected/curated JSON to a TXT report."""

import argparse
import json
import os
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent
CRAWL_DIR = SKILL_DIR / "output" / "crawl"
REPORT_DIR = SKILL_DIR / "output" / "reports"

EDITION_MAP = {
    "morning": {"label": "早报", "title": "AI 科技早报"},
    "evening": {"label": "晚报", "title": "AI 科技晚报"},
}


def load_news_items(path):
    with Path(path).open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("items"), list):
        return payload["items"]
    raise ValueError("JSON 必须是新闻数组，或包含 items 数组的模块一输出")


def format_tags(tags):
    if isinstance(tags, list):
        return " / ".join(str(tag).strip() for tag in tags if str(tag).strip())
    return str(tags or "").strip()


def create_report(output_path, title, date_str, news_items):
    lines = [title, f"日期：{date_str}", "", "=" * 64, ""]
    if not news_items:
        lines.extend(["本期暂无符合条件的 AI 相关新闻。", ""])
    for index, item in enumerate(news_items, 1):
        lines.extend([f"{index}. {str(item.get('title', '')).strip()}", "-" * 64])
        if item.get("summary"):
            lines.append(f"摘要：{str(item['summary']).strip()}")
        tags = format_tags(item.get("tags"))
        if tags:
            lines.append(f"标签：{tags}")
        if item.get("source_count"):
            lines.append(f"来源数：{item['source_count']}")
        elif item.get("source_name") or item.get("platform"):
            lines.append(f"来源：{item.get('source_name') or item.get('platform')}")
        if item.get("relevance_score") is not None:
            lines.append(f"AI 相关性：{item['relevance_score']}/100")
        if item.get("match_reason"):
            lines.append(f"匹配原因：{item['match_reason']}")
        if item.get("latest_published_at") or item.get("published_at"):
            lines.append(f"发布时间：{item.get('latest_published_at') or item.get('published_at')}")
        if item.get("url"):
            lines.append(f"原文链接：{item['url']}")
        lines.append("")
    lines.extend(["=" * 64, "由 AI Daily 自动生成", ""])
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_name(f".{output_path.name}.{os.getpid()}.tmp")
    temp_path.write_text("\n".join(lines), encoding="utf-8")
    os.replace(temp_path, output_path)
    print(f"已保存: {output_path}")


def parse_args():
    parser = argparse.ArgumentParser(description="把模块一 JSON 或精选 JSON 转成 TXT")
    parser.add_argument("date")
    parser.add_argument("edition", choices=EDITION_MAP)
    parser.add_argument("items_file", nargs="?")
    return parser.parse_args()


def main():
    args = parse_args()
    source_file = Path(args.items_file) if args.items_file else CRAWL_DIR / args.date / f"{args.date}_{args.edition}.json"
    if not source_file.exists():
        raise SystemExit(f"找不到输入数据: {source_file}")
    try:
        news_items = load_news_items(source_file)
    except (json.JSONDecodeError, ValueError) as exc:
        raise SystemExit(f"输入数据格式错误: {exc}") from exc
    info = EDITION_MAP[args.edition]
    output_path = REPORT_DIR / args.date / info["label"] / f"{args.date}_{info['label']}.txt"
    create_report(output_path, info["title"], args.date, news_items)


if __name__ == "__main__":
    main()
