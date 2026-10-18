import json
from unittest.mock import AsyncMock

import httpx
import pytest
from app.services import gigachat_client as client_module


@pytest.mark.asyncio
@pytest.mark.parametrize("structured", [False, True])
async def test_response_format_is_sent_only_when_requested(monkeypatch, structured):
    captured = []
    def respond(request):
        captured.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}],
                                          "usage": {"prompt_tokens": 1, "completion_tokens": 1}})
    original_client = httpx.AsyncClient
    monkeypatch.setattr(client_module.httpx, "AsyncClient",
                        lambda **kwargs: original_client(transport=httpx.MockTransport(respond)))
    monkeypatch.setattr(client_module, "build_gigachat_ssl_context", lambda: True)
    client = client_module.GigaChatAutoToken()
    client.get_valid_token = AsyncMock(return_value="test-token")
    schema = {"type": "json_schema", "strict": True, "schema": {"type": "object"}}
    result = await client.chat_completion([{"role": "user", "content": "test"}], "test-model",
                                          response_format=schema if structured else None)
    assert result.content == "{}"
    if structured:
        assert captured[0]["response_format"] == schema
    else:
        assert "response_format" not in captured[0]

@pytest.mark.asyncio
@pytest.mark.parametrize("arguments", [{"sufficient": False}, '{"sufficient": false}'])
async def test_forced_function_arguments_are_used_instead_of_content(monkeypatch, arguments):
    captured = []
    def respond(request):
        captured.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {
            "content": "ignored", "function_call": {"name": "extract", "arguments": arguments}}}]})
    original_client = httpx.AsyncClient
    monkeypatch.setattr(client_module.httpx, "AsyncClient",
                        lambda **kwargs: original_client(transport=httpx.MockTransport(respond)))
    monkeypatch.setattr(client_module, "build_gigachat_ssl_context", lambda: True)
    client = client_module.GigaChatAutoToken()
    client.get_valid_token = AsyncMock(return_value="test-token")
    function = {"name": "extract", "parameters": {"type": "object"}}
    result = await client.chat_completion([], "test-model", structured_function=function)
    assert json.loads(result.content) == {"sufficient": False}
    assert captured[0]["functions"] == [function]
    assert captured[0]["function_call"] == {"name": "extract"}
    assert "response_format" not in captured[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("function_call", [None, {"name": "other", "arguments": {}},
                                            {"name": "extract", "arguments": []}])
async def test_invalid_function_response_fails_closed(monkeypatch, function_call):
    original_client = httpx.AsyncClient
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={
        "choices": [{"message": {"content": "{}", "function_call": function_call}}]}))
    monkeypatch.setattr(client_module.httpx, "AsyncClient",
                        lambda **kwargs: original_client(transport=transport))
    monkeypatch.setattr(client_module, "build_gigachat_ssl_context", lambda: True)
    client = client_module.GigaChatAutoToken()
    client.get_valid_token = AsyncMock(return_value="test-token")
    with pytest.raises(RuntimeError):
        await client.chat_completion([], "test-model", structured_function={"name": "extract"})

@pytest.mark.asyncio
async def test_http_error_preserves_status_without_response_body(monkeypatch):
    original_client = httpx.AsyncClient
    transport = httpx.MockTransport(lambda request: httpx.Response(402, text="private-response"))
    monkeypatch.setattr(client_module.httpx, "AsyncClient",
                        lambda **kwargs: original_client(transport=transport))
    monkeypatch.setattr(client_module, "build_gigachat_ssl_context", lambda: True)
    client = client_module.GigaChatAutoToken()
    client.get_valid_token = AsyncMock(return_value="private-token")
    with pytest.raises(client_module.GigaChatAPIError) as caught:
        await client.chat_completion([], "test-model")
    assert caught.value.status_code == 402
    assert "private-response" not in str(caught.value)
    assert "private-token" not in str(caught.value)
