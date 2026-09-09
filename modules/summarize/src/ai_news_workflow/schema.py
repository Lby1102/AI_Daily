from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Any


SCORE_FIELDS = (
    "ai_relevance",
    "pure_ai_software",
    "heat",
    "credibility",
    "recency",
    "content_value",
)


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


def _min_item_chars() -> int:
    return _int_env("SUMMARIZE_MIN_ITEM_CHARS", 400)


def _max_item_chars() -> int:
    return _int_env("SUMMARIZE_MAX_ITEM_CHARS", 600)


def _max_lead_chars() -> int:
    return _int_env("SUMMARIZE_MAX_LEAD_CHARS", 180)


def _max_section_chars() -> int:
    return _int_env("SUMMARIZE_MAX_SECTION_CHARS", 260)


def _paragraph_bounds() -> tuple[int, int]:
    return _int_env("SUMMARIZE_MIN_PARAGRAPHS", 2), _int_env("SUMMARIZE_MAX_PARAGRAPHS", 5)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _score(value: Any) -> float:
    try:
        return max(0.0, min(100.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [text for item in value if (text := _text(item))]


@dataclass(frozen=True)
class ScoreDimensions:
    ai_relevance: float
    pure_ai_software: float
    heat: float
    credibility: float
    recency: float
    content_value: float

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ScoreDimensions":
        return cls(**{field: _score(data.get(field)) for field in SCORE_FIELDS})


@dataclass
class Candidate:
    candidate_id: str
    title: str
    summary: str
    key_facts: list[str]
    background: str
    caveats: list[str]
    source_name: str
    source_url: str
    published_at: str
    heat_evidence: str
    event_key: str
    dimensions: ScoreDimensions
    score_reason: str
    total_score: float = 0.0

    @classmethod
    def from_dict(cls, data: dict[str, Any], fallback_id: str) -> "Candidate":
        return cls(
            candidate_id=_text(data.get("candidate_id")) or fallback_id,
            title=_text(data.get("title")),
            summary=_text(data.get("summary")),
            key_facts=_text_list(data.get("key_facts")),
            background=_text(data.get("background")),
            caveats=_text_list(data.get("caveats")),
            source_name=_text(data.get("source_name")),
            source_url=_text(data.get("source_url")),
            published_at=_text(data.get("published_at")),
            heat_evidence=_text(data.get("heat_evidence")),
            event_key=_text(data.get("event_key")) or _text(data.get("title")),
            dimensions=ScoreDimensions.from_dict(data.get("dimensions") or {}),
            score_reason=_text(data.get("score_reason")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ArticleItem:
    title: str
    lead: str
    paragraphs: list[str]
    source_name: str
    source_url: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ArticleItem":
        return cls(
            title=_text(data.get("title")),
            lead=_text(data.get("lead")),
            paragraphs=_text_list(data.get("paragraphs")),
            source_name=_text(data.get("source_name")),
            source_url=_text(data.get("source_url")),
        )

    @property
    def content_length(self) -> int:
        return len(self.lead) + sum(len(paragraph) for paragraph in self.paragraphs)

    def validate(self, index: int = 1) -> None:
        if not self.title or not self.lead:
            raise ValueError(f"第 {index} 篇文章的标题或开篇为空。")
        if len(self.lead) > _max_lead_chars():
            raise ValueError(f"第 {index} 篇开篇 {len(self.lead)} 字，超过 {_max_lead_chars()} 字上限。")
        para_min, para_max = _paragraph_bounds()
        if not para_min <= len(self.paragraphs) <= para_max:
            raise ValueError(f"第 {index} 篇文章必须包含 {para_min}～{para_max} 个正文段落。")
        char_min = _min_item_chars()
        char_max = _max_item_chars()
        if self.content_length < char_min:
            raise ValueError(
                f"第 {index} 篇文章只有 {self.content_length} 字，低于 {char_min} 字下限，请补充关键事实与数据。"
            )
        if self.content_length > char_max:
            raise ValueError(
                f"第 {index} 篇文章有 {self.content_length} 字，超过 {char_max} 字上限，请删除空话与扩展性句子。"
            )


@dataclass(frozen=True)
class Article:
    title: str
    introduction: str
    items: list[ArticleItem]
    conclusion: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Article":
        raw_items = data.get("items") or []
        items = [ArticleItem.from_dict(item) for item in raw_items if isinstance(item, dict)]
        if len(items) != 5:
            raise ValueError(f"模型应生成 5 条资讯，实际得到 {len(items)} 条。")
        article = cls(
            title=_text(data.get("title")),
            introduction=_text(data.get("introduction")),
            items=items,
            conclusion=_text(data.get("conclusion")),
        )
        if not article.title or not article.introduction or not article.conclusion:
            raise ValueError("模型返回的文章标题、导语或结语为空。")
        if len(article.introduction) > _max_section_chars():
            raise ValueError(f"导语 {len(article.introduction)} 字，超过 {_max_section_chars()} 字上限，请精简。")
        if len(article.conclusion) > _max_section_chars():
            raise ValueError(f"结语 {len(article.conclusion)} 字，超过 {_max_section_chars()} 字上限，请精简。")
        for index, item in enumerate(article.items, start=1):
            item.validate(index)
        return article
