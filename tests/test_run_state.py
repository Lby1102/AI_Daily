from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config import Settings
from app.orchestrator import Orchestrator, OrchestratorError, _create_next_review_dir


class RunStateTests(unittest.TestCase):
    def test_failure_replaces_old_success_and_blocks_push(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            orch = Orchestrator(Settings(data_dir=root / "data", review_dir=root / "review"))
            orch.state.record_last("2026-09-04", "morning", "ok", "old success")
            with patch.object(orch, "_generate_today", side_effect=ValueError("broken JSON")):
                with self.assertRaisesRegex(OrchestratorError, "broken JSON"):
                    orch.run_today("2026-09-08")
            last = orch.state.read().last_run
            self.assertEqual((last.date, last.status), ("2026-09-08", "failed"))
            manifest = json.loads(next((root / "data/runs").glob("*.json")).read_text(encoding="utf-8"))
            self.assertEqual(manifest["error"], "broken JSON")
            with self.assertRaisesRegex(OrchestratorError, "最近一次生成未成功"):
                orch.push_reviewed()

    def test_invalid_date_cannot_reach_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            orch = Orchestrator(Settings(data_dir=Path(directory)))
            with patch.object(orch, "_generate_today") as generate:
                with self.assertRaisesRegex(OrchestratorError, "YYYY-MM-DD"):
                    orch.run_today("../../outside")
                generate.assert_not_called()

    def test_local_auto_enables_json_mode(self):
        settings = Settings(llm_provider="local", summarize_json_mode="auto")
        self.assertEqual(settings.summarize_env(Path("raw"), Path("html"), Path("report"))["DEEPSEEK_JSON_MODE"], "true")

    def test_next_version_continues_after_highest_even_when_base_is_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "2026-09-09-v1").mkdir()
            (root / "2026-09-09-v2").mkdir()
            result, suffix = _create_next_review_dir(root, "2026-09-09")
            self.assertEqual(result.name, "2026-09-09-v3")
            self.assertEqual(suffix, "-v3")


if __name__ == "__main__":
    unittest.main()
