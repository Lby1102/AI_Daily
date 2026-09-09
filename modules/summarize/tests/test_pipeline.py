from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ai_news_workflow.html_renderer import render_article  # noqa: E402
from ai_news_workflow.pipeline import chunk_text, read_required_text, run_pipeline  # noqa: E402
from ai_news_workflow.schema import Article, ArticleItem, Candidate, ScoreDimensions  # noqa: E402


class FakeClient:
    def extract_candidates(self, raw_text: str, feedback: str, chunk_index: int) -> list[Candidate]:
        return [
            Candidate(
                candidate_id=str(index),
                title=f"候选 {index}",
                summary="事实摘要",
                key_facts=["关键事实和数据"],
                background="原文背景",
                caveats=["尚待观察"],
                source_name="测试来源",
                source_url=f"https://example.com/{index}",
                published_at="2026-09-01",
                heat_evidence="热度数据",
                event_key=f"event-{index}",
                dimensions=ScoreDimensions(90, 90 - index, 85 - index, 90, 90, 85),
                score_reason="测试评分",
            )
            for index in range(1, 7)
        ]

    def generate_article(self, selected: list[Candidate], feedback: str) -> Article:
        return Article(
            title="测试简报",
            introduction="测试导语",
            items=[
                ArticleItem(
                    item.title,
                    "事件开篇",
                    ["关键事实", "原文背景", "关注意义"],
                    item.source_name,
                    item.source_url,
                )
                for item in selected
            ],
            conclusion="测试结语",
        )


class PipelineTests(unittest.TestCase):
    def test_article_contract_rejects_short_sections(self) -> None:
        data = {
            "title": "标题",
            "introduction": "导语",
            "items": [
                {
                    "title": f"文章 {index}",
                    "lead": "过短开篇",
                    "paragraphs": ["事实", "背景", "影响"],
                    "source_name": "来源",
                    "source_url": f"https://example.com/{index}",
                }
                for index in range(5)
            ],
            "conclusion": "结语",
        }
        with self.assertRaisesRegex(ValueError, r"低于 \d+ 字下限"):
            Article.from_dict(data)

    def test_chunk_text_preserves_content(self) -> None:
        text = "A" * 900 + "\n" + "B" * 900
        chunks = chunk_text(text, 1000)
        self.assertEqual("".join(chunks), text.replace("\n", ""))
        self.assertEqual(len(chunks), 2)

    def test_empty_input_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "empty.txt"
            path.write_text(" \n ", encoding="utf-8")
            with self.assertRaises(ValueError):
                read_required_text(path, "测试文件")

    def test_html_escapes_model_text(self) -> None:
        article = Article(
            title="<script>标题</script>",
            introduction="导语 & 内容",
            items=[ArticleItem(f"新闻{i}", "开篇", ["事实", "背景", "影响"],
                               f"来源{i}", f"https://example.com/{i}")
                   for i in range(1, 6)],
            conclusion="结语",
        )
        html = render_article(article, PROJECT_ROOT / "templates/article.html")
        self.assertNotIn("<script>标题</script>", html)
        self.assertIn("&lt;script&gt;标题&lt;/script&gt;", html)
        self.assertIn("https://example.com/1", html)

    def test_full_pipeline_writes_html_and_scoring_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = root / "raw.txt"
            feedback = root / "feedback.txt"
            output = root / "article.html"
            report = root / "scoring.json"
            raw.write_text("三条带来源和热度的 AI 资讯", encoding="utf-8")
            feedback.write_text("标题保持克制", encoding="utf-8")

            ranking = run_pipeline(
                client=FakeClient(),
                raw_path=raw,
                feedback_path=feedback,
                output_path=output,
                report_path=report,
                template_path=PROJECT_ROOT / "templates/article.html",
                max_input_chars=1000,
            )

            self.assertEqual(len(ranking.selected), 5)
            self.assertTrue(output.exists())
            self.assertTrue(report.exists())
            self.assertIn("测试简报", output.read_text(encoding="utf-8"))
            self.assertIn('"selected"', report.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
