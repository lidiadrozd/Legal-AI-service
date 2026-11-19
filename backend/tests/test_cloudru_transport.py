"""Offline transport checks; runnable directly without database fixtures."""
import asyncio
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from app.services import gigachat_client as module


class CloudRuTests(unittest.IsolatedAsyncioTestCase):
    async def request(self, reply, **kwargs):
        requests = []
        def respond(request):
            requests.append(request)
            return httpx.Response(200, json={
                "choices": [{"message": {"content": reply}}],
                "usage": {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6},
            })
        client = module.CloudRuClient()
        client._http_client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        try:
            with patch.object(module.settings, 'CLOUDRU_API_KEY', 'test-secret'), \
                 patch.object(module.settings, 'CLOUDRU_MODEL', 'test-cloud-model'):
                result = await client.chat_completion(
                    [{"role": "user", "content": "test"}], 'GigaChat', **kwargs)
            self.assertEqual(len(requests), 1)
            self.assertEqual(str(requests[0].url),
                             'https://foundation-models.api.cloud.ru/v1/chat/completions')
            self.assertEqual(requests[0].headers['Authorization'], 'Bearer test-secret')
            self.assertEqual(json.loads(requests[0].content)['model'], 'test-cloud-model')
            self.assertEqual(result.usage.total_tokens, 6)
            return result
        finally:
            await client.aclose()

    async def test_text_without_oauth(self):
        self.assertEqual((await self.request('Works')).content, 'Works')

    async def test_structured_function(self):
        result = await self.request('{"ok": true}', structured_function={
            'name': 'extract', 'parameters': {'type': 'object'}})
        self.assertTrue(json.loads(result.content)['ok'])

    async def test_invalid_json_rejected(self):
        for reply in ('not JSON', '[]', 'null'):
            with self.assertRaises(RuntimeError):
                await self.request(reply, response_format={'type': 'json_object'})

    async def test_missing_key(self):
        with patch.object(module.settings, 'CLOUDRU_API_KEY', ''):
            with self.assertRaises(RuntimeError):
                await module.CloudRuClient().get_valid_token()

    async def test_http_error_does_not_expose_body(self):
        client = module.CloudRuClient()
        client._http_client = httpx.AsyncClient(transport=httpx.MockTransport(
            lambda request: httpx.Response(401, text='secret-response')))
        try:
            with patch.object(module.settings, 'CLOUDRU_API_KEY', 'test-secret'):
                with self.assertRaises(module.GigaChatAPIError) as caught:
                    await client.chat_completion([], 'ignored')
            self.assertEqual(caught.exception.status_code, 401)
            self.assertNotIn('secret', str(caught.exception))
        finally:
            await client.aclose()


if __name__ == '__main__':
    unittest.main()
