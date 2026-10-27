"""Offline checks for the local voice token boundary."""

import importlib.util
import io
import json
import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

MODULE_PATH = Path(__file__).resolve().parent.parent / 'examples' / 'llm_example.py'
spec = importlib.util.spec_from_file_location('examples.llm_example', MODULE_PATH)
voice = importlib.util.module_from_spec(spec)
spec.loader.exec_module(voice)


class VoiceServerTests(unittest.TestCase):
    def test_missing_key_does_not_make_request(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(voice, 'urlopen') as upstream:
            with self.assertRaisesRegex(voice.VoiceSetupError, 'OPENAI_API_KEY is missing'):
                voice.create_client_secret()
            upstream.assert_not_called()

    def test_returns_short_lived_token_without_project_key(self):
        response = MagicMock()
        response.__enter__.return_value = io.StringIO(json.dumps({
            'value': 'synthetic-session-token', 'expires_at': 123,
        }))
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'synthetic-project-key'}), patch.object(voice, 'urlopen', return_value=response) as upstream:
            result = voice.create_client_secret()
        self.assertEqual(result['value'], 'synthetic-session-token')
        self.assertNotIn('synthetic-project-key', json.dumps(result))
        request = upstream.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(payload['session']['model'], 'gpt-realtime-2.1')
        self.assertEqual(payload['session']['audio']['output']['voice'], 'cedar')
        self.assertEqual(payload['session']['max_output_tokens'], 4096)
        self.assertEqual({tool['name'] for tool in payload['session']['tools']}, {'search_gmail', 'read_gmail_email', 'search_crowdmark'})
        self.assertEqual(payload['expires_after']['seconds'], 60)
        self.assertEqual(request.get_header('Authorization'), 'Bearer synthetic-project-key')

    def test_auth_error_does_not_leak_upstream_content(self):
        error = HTTPError('https://api.openai.com', 401, 'Unauthorized', {}, io.BytesIO(b'private upstream details'))
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'synthetic-project-key'}), patch.object(voice, 'urlopen', side_effect=error):
            with self.assertRaises(voice.VoiceSetupError) as caught:
                voice.create_client_secret()
        self.assertNotIn('private upstream details', str(caught.exception))
        self.assertIn('rejected the API key', str(caught.exception))

    def test_unexpected_origin_cannot_mint_token(self):
        handler = object.__new__(voice.VoiceHandler)
        handler.path = '/api/realtime/token'
        handler.headers = {'Origin': 'https://untrusted.example', 'X-Jarvis-Voice': '1'}
        handler.respond = MagicMock()
        with patch.object(voice, 'create_client_secret') as create:
            handler.do_POST()
            create.assert_not_called()
        self.assertEqual(handler.respond.call_args.args[0], 403)

    def test_expected_browser_request_can_mint_token(self):
        handler = object.__new__(voice.VoiceHandler)
        handler.path = '/api/realtime/token'
        handler.headers = {'Origin': 'http://127.0.0.1:5173', 'X-Jarvis-Voice': '1'}
        handler.respond = MagicMock()
        with patch.object(voice, 'create_client_secret', return_value={'value': 'synthetic'}) as create:
            handler.do_POST()
            create.assert_called_once_with()
        handler.respond.assert_called_once_with(200, {'value': 'synthetic'})

    def test_plain_post_cannot_mint_token(self):
        handler = object.__new__(voice.VoiceHandler)
        handler.path = '/api/realtime/token'
        handler.headers = {}
        handler.respond = MagicMock()
        with patch.object(voice, 'create_client_secret') as create:
            handler.do_POST()
            create.assert_not_called()
        self.assertEqual(handler.respond.call_args.args[0], 403)

    def test_email_tool_route_passes_only_name_and_arguments(self):
        handler = object.__new__(voice.VoiceHandler)
        handler.path = '/api/realtime/tool'
        payload = json.dumps({'name': 'search_gmail', 'arguments': {'query': 'assignment'}}).encode()
        handler.headers = {'X-Jarvis-Voice': '1', 'Content-Length': str(len(payload))}
        handler.rfile = io.BytesIO(payload)
        handler.respond = MagicMock()
        with patch.object(voice, 'lookup_gmail', return_value={'count': 0}) as lookup:
            handler.do_POST()
            lookup.assert_called_once_with('search_gmail', {'query': 'assignment'})
        handler.respond.assert_called_once_with(200, {'count': 0})

    def test_email_tool_route_rejects_malformed_payload(self):
        handler = object.__new__(voice.VoiceHandler)
        handler.path = '/api/realtime/tool'
        handler.headers = {'X-Jarvis-Voice': '1', 'Content-Length': '3'}
        handler.rfile = io.BytesIO(b'bad')
        handler.respond = MagicMock()
        with patch.object(voice, 'lookup_gmail') as lookup:
            handler.do_POST()
            lookup.assert_not_called()
        self.assertEqual(handler.respond.call_args.args[0], 400)


if __name__ == '__main__':
    unittest.main()
