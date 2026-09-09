import tempfile
import unittest
import os
from pathlib import Path
from unittest.mock import patch

from app.review_picker import choose_article
from app.orchestrator import Orchestrator, OrchestratorError
from app.config import Settings
from app.control import main


class ReviewPickerTests(unittest.TestCase):
    def test_choose_exact_version_after_invalid_input(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for folder in ("2026-09-09", "2026-09-09-v2"):
                (root / folder).mkdir()
                (root / folder / "article.html").write_text('<h1>News</h1>', encoding='utf-8')
            os.utime(root / '2026-09-09/article.html', (1, 1))
            os.utime(root / '2026-09-09-v2/article.html', (2, 2))
            with patch('builtins.input', side_effect=['wrong', '99', '1']):
                selected = choose_article(root)
            self.assertEqual(selected, root / '2026-09-09-v2/article.html')

    def test_cancel_never_calls_upload(self):
        with patch('app.control.choose_article', return_value=None), patch.object(Orchestrator, 'push_reviewed') as push:
            self.assertEqual(main(['push']), 0)
            push.assert_not_called()

    def test_selected_file_and_its_cover_are_passed_to_module(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / 'review/2026-09-09-v2'
            folder.mkdir(parents=True)
            article = folder / 'edited.html'
            article.write_text('<h1>News</h1>')
            (folder / 'cover.png').write_bytes(b'cover')
            settings = Settings(review_dir=root/'review', data_dir=root/'data', wechat_app_id='test', wechat_app_secret='test')
            with patch('app.orchestrator._run_live') as run:
                Orchestrator(settings).push_reviewed(article_path=article)
            env = run.call_args.kwargs['env']
            self.assertEqual(Path(env['ARTICLE_HTML']), article.resolve())
            self.assertEqual(Path(env['COVER_IMAGE']), (folder/'cover.png').resolve())
            with self.assertRaises(OrchestratorError):
                Orchestrator(settings).push_reviewed(article_path=root/'outside.html')
