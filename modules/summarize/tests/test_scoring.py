from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ai_news_workflow.schema import Candidate, ScoreDimensions  # noqa: E402
from ai_news_workflow.scoring import calculate_total, rank_candidates  # noqa: E402


def candidate(
    title: str,
    event_key: str,
    dimensions: tuple[float, float, float, float, float, float],
    url: str = "https://example.com/news",
) -> Candidate:
    return Candidate(
        candidate_id=title,
        title=title,
        summary="有效摘要",
        key_facts=["关键事实"],
        background="背景",
        caveats=["限制"],
        source_name="测试来源",
        source_url=url,
        published_at="2026-09-01",
        heat_evidence="1000 次阅读",
        event_key=event_key,
        dimensions=ScoreDimensions(*dimensions),
        score_reason="测试理由",
    )


class ScoringTests(unittest.TestCase):
    def test_weighted_total(self) -> None:
        item = candidate("A", "A-event", (100, 100, 100, 100, 100, 100))
        self.assertEqual(calculate_total(item), 100.0)

    def test_pure_ai_software_bonus_affects_ranking(self) -> None:
        software = candidate("软件", "software-event", (85, 100, 70, 80, 80, 80))
        hardware = candidate("芯片", "hardware-event", (85, 20, 70, 80, 80, 80))
        ranking = rank_candidates([hardware, software])
        self.assertEqual(ranking.selected[0].title, "软件")
        self.assertGreater(software.total_score, hardware.total_score)

    def test_hard_gate_rejects_weak_ai_relation(self) -> None:
        weak = candidate("弱相关", "weak-event", (59, 90, 90, 90, 90, 90))
        ranking = rank_candidates([weak])
        self.assertEqual(ranking.selected, [])
        self.assertIn("AI 相关性", ranking.rejected[0].reason)

    def test_duplicate_event_keeps_higher_score(self) -> None:
        low = candidate("旧版本", "same-event", (70, 60, 50, 60, 60, 60))
        high = candidate("高质量版本", "same-event", (90, 80, 80, 90, 90, 90))
        ranking = rank_candidates([low, high])
        self.assertEqual(len(ranking.eligible), 1)
        self.assertEqual(ranking.selected[0].title, "高质量版本")

    def test_invalid_source_url_is_rejected(self) -> None:
        unsafe = candidate("错误链接", "unsafe-event", (90, 90, 90, 90, 90, 90), "javascript:alert(1)")
        ranking = rank_candidates([unsafe])
        self.assertEqual(ranking.selected, [])
        self.assertIn("原文链接", ranking.rejected[0].reason)


if __name__ == "__main__":
    unittest.main()
