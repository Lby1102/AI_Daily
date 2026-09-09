from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from .html_renderer import render_article
from .scoring import RankingResult, rank_candidates

if TYPE_CHECKING:
    from .deepseek_client import DeepSeekClient


def read_required_text(path: Path, label: str) -> str:
    if not path.exists():
        raise FileNotFoundError(f"{label}不存在：{path}")
    content = path.read_text(encoding="utf-8-sig")
    normalized = "\n".join(line.rstrip() for line in content.replace("\r\n", "\n").split("\n"))
    if not normalized.strip():
        raise ValueError(f"{label}为空：{path}")
    return normalized.strip()


def read_optional_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8-sig").strip()


def chunk_text(text: str, max_chars: int) -> list[str]:
    if max_chars < 1000:
        raise ValueError("DEEPSEEK_MAX_INPUT_CHARS 不能小于 1000")
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            split_at = text.rfind("\n", start, end)
            if split_at > start + max_chars // 2:
                end = split_at
        chunks.append(text[start:end].strip())
        start = end
    return [chunk for chunk in chunks if chunk]


def build_scoring_report(ranking: RankingResult) -> dict[str, object]:
    return {
        "selected": [candidate.to_dict() for candidate in ranking.selected],
        "eligible": [candidate.to_dict() for candidate in ranking.eligible],
        "rejected": [
            {"reason": item.reason, "candidate": item.candidate.to_dict()}
            for item in ranking.rejected
        ],
    }


def run_pipeline(
    client: "DeepSeekClient",
    raw_path: Path,
    feedback_path: Path,
    output_path: Path,
    report_path: Path,
    template_path: Path,
    max_input_chars: int,
) -> RankingResult:
    raw_text = read_required_text(raw_path, "原始资讯文件")
    feedback = read_optional_text(feedback_path)

    candidates = []
    chunks = chunk_text(raw_text, max_input_chars)
    for index, chunk in enumerate(chunks, start=1):
        print(f"抽取候选 {index}/{len(chunks)}（{len(chunk)} 字符）…", flush=True)
        candidates.extend(client.extract_candidates(chunk, feedback, index))
        print(f"已抽取 {len(candidates)} 条候选", flush=True)

    ranking = rank_candidates(candidates, limit=5)
    if len(ranking.selected) < 5:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(build_scoring_report(ranking), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        raise ValueError(
            f"通过门槛且去重后只有 {len(ranking.selected)} 条资讯，不足 5 条；"
            f"请查看评分报告：{report_path}"
        )

    print("已选定 5 条资讯，正在生成正文…", flush=True)
    article = client.generate_article(ranking.selected, feedback)
    html = render_article(article, template_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(build_scoring_report(ranking), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return ranking
