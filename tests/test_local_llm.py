"""Local LLM provider (LM Studio / Ollama, OpenAI-compatible API). The HTTP layer is mocked: no server, no network."""

import json

import httpx
import pytest

from p14_search.answer.llm import LLMClient, LLMError, LocalProvider, build_llm
from p14_search.config import Settings


def reply(text: str, tokens_in: int = 12, tokens_out: int = 5, usage: bool = True) -> dict:
    body = {"id": "chatcmpl-test", "object": "chat.completion", "created": 0, "model": "test-model",
            "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": text}}]}
    if usage:
        body["usage"] = {"prompt_tokens": tokens_in, "completion_tokens": tokens_out, "total_tokens": tokens_in + tokens_out}
    return body


class Server:
    """Stands in for the local server and records every request it receives."""

    def __init__(self, body: dict | None = None, status: int = 200):
        self.body = body or reply("La scadenza è il 28 agosto 2026. [P1]")
        self.status = status
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(self.status, json=self.body)

    def provider(self, base_url: str = "http://127.0.0.1:1234/v1") -> LocalProvider:
        return LocalProvider("test-model", base_url, http_client=httpx.Client(transport=httpx.MockTransport(self)))


def client(provider, tmp_path, **settings) -> LLMClient:
    return build_llm(Settings(_env_file=None, llm_cache_dir=tmp_path / "cache", llm_usage_log=tmp_path / "usage.jsonl", **settings),
                     provider)


def test_request_goes_to_the_local_server_with_temperature_zero():
    server = Server()
    text, tokens_in, tokens_out = server.provider().call("system text", "user text", 600)
    assert (text, tokens_in, tokens_out) == ("La scadenza è il 28 agosto 2026. [P1]", 12, 5)
    request = server.requests[0]
    assert str(request.url) == "http://127.0.0.1:1234/v1/chat/completions"
    sent = json.loads(request.content)
    assert sent["model"] == "test-model" and sent["temperature"] == 0 and sent["max_tokens"] == 600
    assert sent["messages"] == [{"role": "system", "content": "system text"}, {"role": "user", "content": "user text"}]


def test_ollama_base_url_is_used_as_given():
    server = Server()
    server.provider("http://127.0.0.1:11434/v1").call("s", "p", 10)
    assert str(server.requests[0].url) == "http://127.0.0.1:11434/v1/chat/completions"


def test_settings_build_a_local_client_without_an_api_key():
    llm = build_llm(Settings(_env_file=None, llm_provider="local", llm_model="some-model", llm_api_key="",
                             llm_base_url="http://127.0.0.1:11434/v1", llm_timeout_s=7))
    assert llm.name == "local:some-model" and llm.price == (0.0, 0.0)
    assert llm.provider.base_url == "http://127.0.0.1:11434/v1" and llm.provider.client.timeout == 7
    assert Settings(_env_file=None).llm_base_url == "http://127.0.0.1:1234/v1"  # default = LM Studio
    assert build_llm(Settings(_env_file=None, llm_provider="local", llm_model="")) is None  # no model = extractive


def test_local_calls_cost_nothing_and_are_cached_and_logged(tmp_path):
    server = Server()
    llm = client(server.provider(), tmp_path)
    first = llm.complete("system", "prompt", 50, "answer")
    again = llm.complete("system", "prompt", 50, "answer")
    assert first.cost_usd == 0.0 and not first.cached and again.cached and again.text == first.text
    assert len(server.requests) == 1  # the second answer came from the disk cache
    rows = [json.loads(x) for x in (tmp_path / "usage.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [(r["provider"], r["model"], r["cost_usd"], r["cached"]) for r in rows] == [
        ("local", "test-model", 0.0, False), ("local", "test-model", 0.0, True)]


def test_budget_never_blocks_local_calls(tmp_path):
    usage = tmp_path / "usage.jsonl"
    usage.write_text('{"cost_usd": 99.0, "cached": false}\n', encoding="utf-8")  # paid calls already above the limit
    # price overrides in the settings belong to the paid providers: a local call stays free
    llm = client(Server().provider(), tmp_path, llm_budget_usd=5.0, llm_price_in_per_mtok=1.0, llm_price_out_per_mtok=2.0)
    assert llm.spent_usd() == 99.0
    assert llm.complete("system", "prompt", 50, "answer").cost_usd == 0.0


def test_cache_key_separates_local_from_other_providers(tmp_path):
    from p14_search.answer.llm import FakeProvider

    client(FakeProvider(lambda s, p: "fake text", model="test-model"), tmp_path).complete("system", "prompt", 50, "answer")
    server = Server()
    result = client(server.provider(), tmp_path).complete("system", "prompt", 50, "answer")
    assert not result.cached and len(server.requests) == 1  # same model name and prompt, different provider


def test_reasoning_block_is_removed_and_missing_usage_is_tolerated():
    server = Server(reply("<think>the passage says 28 August</think>\nyes", usage=False))
    assert server.provider().call("s", "p", 10) == ("yes", 0, 0)


def test_server_error_becomes_llm_error(tmp_path):
    llm = client(Server(status=500).provider(), tmp_path)
    with pytest.raises(LLMError):  # the answer service catches it and falls back to extractive
        llm.complete("system", "prompt", 50, "answer")


def test_server_not_running_becomes_llm_error(tmp_path):
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    provider = LocalProvider("test-model", "http://127.0.0.1:1234/v1", http_client=httpx.Client(transport=httpx.MockTransport(refuse)))
    with pytest.raises(LLMError):
        client(provider, tmp_path).complete("system", "prompt", 50, "answer")
