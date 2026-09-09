import unittest
from unittest.mock import Mock, patch

from wechat_draft_pusher.wechat_api import WeChatAPI, WeChatAPIError
from wechat_draft_pusher import cli


class ApiErrorTests(unittest.TestCase):
    def test_draft_json_is_utf8_without_unicode_escapes(self):
        api = WeChatAPI('app', 'secret')
        api._access_token = 'token'
        response = Mock(ok=True)
        response.json.return_value = {'media_id': 'draft-id'}
        api.session.post = Mock(return_value=response)
        self.assertEqual(api.add_draft({'title': '中文标题', 'content': '<p>中文正文</p>'}), 'draft-id')
        request = api.session.post.call_args
        body = request.kwargs['data']
        self.assertIsInstance(body, bytes)
        self.assertIn('中文标题'.encode('utf-8'), body)
        self.assertNotIn(b'\\u4e2d', body)
        self.assertEqual(request.kwargs['headers']['Content-Type'], 'application/json; charset=utf-8')

    def test_whitelist_message_contains_actionable_ip(self):
        response = Mock(ok=True)
        response.json.return_value = {'errcode':40164, 'errmsg':'invalid ip 192.0.2.11 ipv6 ::ffff:192.0.2.11, not in whitelist'}
        with self.assertRaises(WeChatAPIError) as result:
            WeChatAPI._json_or_raise(response)
        self.assertIn('添加 192.0.2.11', str(result.exception))
        self.assertIn('无需重新生成', str(result.exception))

    def test_expected_error_has_no_traceback(self):
        with patch('sys.argv', ['wechat', 'push']), patch.object(cli.Settings, 'load'), patch.object(cli, 'push_once', side_effect=WeChatAPIError('40164 whitelist')):
            with self.assertLogs(cli.LOGGER, level='ERROR') as logs:
                self.assertEqual(cli.main(), 1)
        self.assertIsNone(logs.records[0].exc_info)
