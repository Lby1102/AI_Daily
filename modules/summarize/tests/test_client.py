from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ai_news_workflow.config import Settings
from ai_news_workflow.deepseek_client import DeepSeekClient
from ai_news_workflow.schema import Candidate, ScoreDimensions


def response(content, finish_reason="stop"):
    return SimpleNamespace(choices=[SimpleNamespace(
        message=SimpleNamespace(content=content), finish_reason=finish_reason)])


class ClientTests(unittest.TestCase):
    def client(self, replies, retries=0):
        client = DeepSeekClient.__new__(DeepSeekClient)
        client.settings = Settings("local", "http://127.0.0.1:8080/v1", "test", 16000, retries)
        client.client = Mock()
        client.client.chat.completions.create.side_effect = replies
        return client

    @patch.dict(os.environ, {"DEEPSEEK_JSON_MODE": "true"})
    def test_local_requests_constrained_json_and_disables_thinking(self):
        client = self.client([response('{"ok": true}')])
        self.assertEqual(client._json_completion("system", "user"), {"ok": True})
        kwargs = client.client.chat.completions.create.call_args.kwargs
        self.assertEqual(kwargs["response_format"]["type"], "json_schema")
        self.assertEqual(kwargs["response_format"]["json_schema"]["schema"], {"type": "object"})
        self.assertFalse(kwargs["extra_body"]["chat_template_kwargs"]["enable_thinking"])

    def test_malformed_json_retries_then_accepts_valid_object(self):
        client = self.client([response('{"title":"bad "quote""}'), response('{"ok":true}')], 1)
        self.assertEqual(client._json_completion("system", "user"), {"ok": True})
        self.assertEqual(client.client.chat.completions.create.call_count, 2)

    def test_length_finish_is_rejected_even_if_content_parses(self):
        client = self.client([response('{"ok":true}', "length")])
        with self.assertRaisesRegex(RuntimeError, "token 上限"):
            client._json_completion("system", "user")

    def test_exhausted_retries_raise(self):
        client = self.client([response("not json"), response("not json")], 1)
        with self.assertRaisesRegex(RuntimeError, "重试后仍失败"):
            client._json_completion("system", "user")

    def test_five_items_are_generated_separately_then_joined(self):
        client = DeepSeekClient.__new__(DeepSeekClient)
        client.settings = Settings("local", "http://127.0.0.1:8080/v1", "test", 16000, 0)
        item = {
            "title": "单篇标题",
            "lead": "开篇" * 30,
            "paragraphs": ["事实" * 60, "背景" * 60, "观察" * 60],
            "source_name": "来源",
            "source_url": "https://example.com/news",
        }
        client._json_completion = Mock(side_effect=[item.copy() for _ in range(5)] + [{
            "title": "五篇简报", "introduction": "导语", "conclusion": "结语"
        }])
        candidates = [Candidate(
            candidate_id=str(i), title=f"候选{i}", summary="摘要", key_facts=["事实"],
            background="背景", caveats=["限制"], source_name="来源",
            source_url=f"https://example.com/{i}", published_at="2026-09-09",
            heat_evidence="热度", event_key=f"event-{i}",
            dimensions=ScoreDimensions(90, 90, 90, 90, 90, 90), score_reason="理由"
        ) for i in range(5)]
        article = client.generate_article(candidates, "")
        self.assertEqual(len(article.items), 5)
        self.assertEqual(client._json_completion.call_count, 6)


if __name__ == "__main__":
    unittest.main()
