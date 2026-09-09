import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent


def load_module(name, filename):
    spec = importlib.util.spec_from_file_location(name, SKILL_DIR / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ai_daily = load_module("ai_daily", "ai_daily.py")
generate_report = load_module("generate_report", "generate_report.py")


class RelevanceTests(unittest.TestCase):
    def test_english_keywords_require_boundaries(self):
        for title in (
            "Farm revenue rises after acquisition",
            "Metadata startup raises funding",
            "GarageBand acquisition rumor",
        ):
            self.assertEqual(ai_daily.score_relevance(title)[0], 0, title)

    def test_general_tech_company_does_not_trigger_by_itself(self):
        self.assertEqual(ai_daily.score_relevance("Apple profit rises")[0], 0)
        self.assertEqual(ai_daily.score_relevance("Google faces antitrust lawsuit")[0], 0)

    def test_core_and_industry_titles_are_retained(self):
        self.assertGreaterEqual(ai_daily.score_relevance("OpenAI releases a new reasoning model")[0], 70)
        self.assertGreaterEqual(ai_daily.score_relevance("SK hynix HBM orders and capacity increase")[0], 50)
        self.assertGreaterEqual(ai_daily.score_relevance("HBM4 enters mass production")[0], 35)
        self.assertGreaterEqual(ai_daily.score_relevance("海光信息股价上涨")[0], 35)

    def test_trusted_ai_source_has_floor(self):
        result = ai_daily.evaluate_relevance("A novel approach to protein design", source_floor=55)
        self.assertEqual(result["score"], 55)
        self.assertEqual(result["reason"], "AI 垂直来源")


class DeduplicationTests(unittest.TestCase):
    def make_item(self, source_id, source_name, title, url, rank=1):
        return ai_daily.build_item(
            {"id": source_id, "name": source_name, "provider": "test"},
            rank,
            title,
            url,
            source_floor=55,
        )

    def test_same_title_different_urls_are_merged(self):
        raw = {
            "weibo": [self.make_item("weibo", "微博", "OpenAI 发布新模型", "https://weibo.example/a")],
            "zhihu": [self.make_item("zhihu", "知乎", "OpenAI发布新模型", "https://zhihu.example/b", 2)],
        }
        result = ai_daily.deduplicate_news(raw)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["source_count"], 2)
        self.assertEqual(len(result[0]["sources"]), 2)

    def test_tracking_parameters_do_not_prevent_url_dedup(self):
        left = "https://example.com/story?id=1&utm_source=x"
        right = "https://www.example.com/story?id=1&utm_medium=y"
        self.assertEqual(ai_daily.canonicalize_url(left), ai_daily.canonicalize_url(right))

    def test_different_model_versions_are_not_merged(self):
        self.assertFalse(ai_daily.titles_similar("openai发布gpt6模型", "openai发布gpt7模型"))

    def test_google_news_publisher_suffix_deduplicates_with_original(self):
        direct = self.make_item("direct", "原站", "OpenAI 发布新模型", "https://example.com/story")
        google = ai_daily.build_item(
            {"id": "google-news:publisher", "name": "原站", "provider": "google_news_rss"},
            2,
            "OpenAI 发布新模型 - 原站",
            "https://news.google.com/story",
            source_floor=55,
            duplicate_title=ai_daily.remove_publisher_suffix("OpenAI 发布新模型 - 原站", "原站"),
        )
        result = ai_daily.deduplicate_news({"direct": [direct], "google": [google]})
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["source_count"], 2)


class ParserAndContractTests(unittest.TestCase):
    def test_rss_and_atom_dates_are_parsed(self):
        rss = """<?xml version='1.0'?><rss><channel><item><title>AI news - Example</title><link>https://example.com/a</link><pubDate>Mon, 01 Sep 2026 08:00:00 GMT</pubDate><source>Example</source></item></channel></rss>"""
        items = ai_daily.parse_feed(rss)
        self.assertEqual(items[0]["title"], "AI news - Example")
        self.assertEqual(items[0]["publisher"], "Example")
        self.assertTrue(items[0]["published_at"].startswith("2026-09-01T08:00:00"))

    def test_naive_newsnow_time_is_interpreted_as_china_time(self):
        parsed = ai_daily.parse_datetime("2026-09-01 16:00:00", default_tz=ai_daily.CHINA_TIMEZONE)
        self.assertEqual(parsed, "2026-09-01T08:00:00+00:00")

    def test_report_loader_accepts_module_one_contract(self):
        payload = {"meta": {"schema_version": "2.0"}, "items": [{"title": "OpenAI test"}], "raw_by_source": {}}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "input.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            self.assertEqual(generate_report.load_news_items(path), payload["items"])

    def test_checked_in_source_config_matches_fallback(self):
        checked_in = json.loads((SKILL_DIR / "sources.json").read_text(encoding="utf-8"))
        fallback = ai_daily.default_config()
        self.assertEqual(checked_in, fallback)
        self.assertEqual(checked_in["lookback_hours"], 12)


if __name__ == "__main__":
    unittest.main()
