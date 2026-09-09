from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from .schema import Candidate


# 总权重为 1.00。纯 AI 软件偏好独立占 15%，足以影响排序但不会压过可信度。
WEIGHTS: dict[str, float] = {
    "ai_relevance": 0.25,
    "pure_ai_software": 0.15,
    "heat": 0.20,
    "credibility": 0.20,
    "recency": 0.10,
    "content_value": 0.10,
}

MIN_AI_RELEVANCE = 60.0
MIN_CREDIBILITY = 40.0


@dataclass(frozen=True)
class RejectedCandidate:
    candidate: Candidate
    reason: str


@dataclass(frozen=True)
class RankingResult:
    selected: list[Candidate]
    eligible: list[Candidate]
    rejected: list[RejectedCandidate]


def calculate_total(candidate: Candidate) -> float:
    dimensions = candidate.dimensions
    total = sum(getattr(dimensions, name) * weight for name, weight in WEIGHTS.items())
    return round(total, 2)


def _valid_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def rejection_reason(candidate: Candidate) -> str | None:
    if not candidate.title or not candidate.summary:
        return "标题或摘要为空"
    if candidate.dimensions.ai_relevance < MIN_AI_RELEVANCE:
        return f"AI 相关性低于 {MIN_AI_RELEVANCE:.0f} 分"
    if candidate.dimensions.credibility < MIN_CREDIBILITY:
        return f"可信度低于 {MIN_CREDIBILITY:.0f} 分"
    if not candidate.source_name:
        return "缺少来源名称"
    if not _valid_http_url(candidate.source_url):
        return "缺少合法的 HTTP/HTTPS 原文链接"
    return None


def rank_candidates(candidates: list[Candidate], limit: int = 2) -> RankingResult:
    rejected: list[RejectedCandidate] = []
    eligible: list[Candidate] = []

    for candidate in candidates:
        candidate.total_score = calculate_total(candidate)
        reason = rejection_reason(candidate)
        if reason:
            rejected.append(RejectedCandidate(candidate, reason))
        else:
            eligible.append(candidate)

    # 同一事件只保留最高分版本。event_key 由模型概括事件主体和动作。
    best_by_event: dict[str, Candidate] = {}
    for candidate in eligible:
        key = " ".join(candidate.event_key.casefold().split())
        previous = best_by_event.get(key)
        if previous is None or candidate.total_score > previous.total_score:
            if previous is not None:
                rejected.append(RejectedCandidate(previous, "同一事件存在更高分版本"))
            best_by_event[key] = candidate
        else:
            rejected.append(RejectedCandidate(candidate, "同一事件存在更高分版本"))

    deduplicated = sorted(best_by_event.values(), key=lambda item: item.total_score, reverse=True)
    return RankingResult(
        selected=deduplicated[:limit],
        eligible=deduplicated,
        rejected=rejected,
    )

