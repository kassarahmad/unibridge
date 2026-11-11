"""LLM providers behind one small interface, with a disk cache, usage log and spend limit.

- Providers: OpenAI or Anthropic (chosen by LLM_PROVIDER), FakeLLM for tests. Tests never call a real API.
- Every call uses temperature 0 and a capped number of output tokens.
- Responses are cached on disk, keyed by SHA-256 of (provider, model, max_tokens, system, prompt): a repeated
  evaluation costs nothing and gives the same text.
- Each call (cached or not) is appended to the usage log with provider, model, tokens and estimated cost.
- Before a non-cached call the estimated spend in the usage log is compared with LLM_BUDGET_USD; above it the
  call is refused (BudgetExceeded) and the caller falls back to extractive answers.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from p14_search.config import Settings

# USD per million tokens (input, output). Used only for cost ESTIMATES; override with LLM_PRICE_*_PER_MTOK.
# gpt-4o-mini: OpenAI price list (0.15 / 0.60). Unknown models give cost None unless overridden.
PRICES = {"gpt-4o-mini": (0.15, 0.60)}
TEMPERATURE = 0.0


class LLMError(RuntimeError):
    pass


class BudgetExceeded(LLMError):
    pass


@dataclass
class LLMResult:
    text: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float | None
    cached: bool
    latency_ms: float


class Provider(Protocol):
    name: str
    model: str

    def call(self, system: str, prompt: str, max_tokens: int) -> tuple[str, int, int]: ...


class OpenAIProvider:
    name = "openai"

    def __init__(self, model: str, api_key: str):
        from openai import OpenAI

        self.model = model
        self.client = OpenAI(api_key=api_key, timeout=60, max_retries=2)

    def call(self, system: str, prompt: str, max_tokens: int) -> tuple[str, int, int]:
        r = self.client.chat.completions.create(
            model=self.model, temperature=TEMPERATURE, max_tokens=max_tokens,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        )
        return r.choices[0].message.content or "", r.usage.prompt_tokens, r.usage.completion_tokens


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, model: str, api_key: str):
        from anthropic import Anthropic

        self.model = model
        self.client = Anthropic(api_key=api_key, timeout=60, max_retries=2)

    def call(self, system: str, prompt: str, max_tokens: int) -> tuple[str, int, int]:
        r = self.client.messages.create(
            model=self.model, temperature=TEMPERATURE, max_tokens=max_tokens, system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in r.content if getattr(b, "type", "") == "text")
        return text, r.usage.input_tokens, r.usage.output_tokens


class FakeProvider:
    """Deterministic provider for tests: `respond(system, prompt) -> text`. Counts calls; no network."""

    name = "fake"

    def __init__(self, respond: Callable[[str, str], str], model: str = "fake-model"):
        self.respond = respond
        self.model = model
        self.calls: list[tuple[str, str]] = []

    def call(self, system: str, prompt: str, max_tokens: int) -> tuple[str, int, int]:
        self.calls.append((system, prompt))
        text = self.respond(system, prompt)
        return text, len((system + prompt).split()), len(text.split())


class LLMClient:
    def __init__(self, provider: Provider, cache_dir: Path | None, usage_log: Path | None, budget_usd: float,
                 price: tuple[float, float] | None):
        self.provider = provider
        self.cache_dir = cache_dir
        self.usage_log = usage_log
        self.budget_usd = budget_usd
        self.price = price
        self._lock = threading.Lock()

    @property
    def name(self) -> str:
        return f"{self.provider.name}:{self.provider.model}"

    def cost(self, input_tokens: int, output_tokens: int) -> float | None:
        if self.price is None:
            return None
        return round((input_tokens * self.price[0] + output_tokens * self.price[1]) / 1e6, 8)

    def spent_usd(self) -> float:
        if not self.usage_log or not self.usage_log.exists():
            return 0.0
        total = 0.0
        for line in self.usage_log.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if not row["cached"] and row["cost_usd"]:
                total += row["cost_usd"]
        return total

    def complete(self, system: str, prompt: str, max_tokens: int, purpose: str) -> LLMResult:
        key = hashlib.sha256(json.dumps([self.provider.name, self.provider.model, max_tokens, TEMPERATURE, system, prompt],
                                        ensure_ascii=False).encode("utf-8")).hexdigest()
        path = self.cache_dir / f"{key}.json" if self.cache_dir else None
        start = time.perf_counter()
        if path and path.exists():
            hit = json.loads(path.read_text(encoding="utf-8"))
            result = LLMResult(hit["text"], self.provider.name, self.provider.model, hit["input_tokens"], hit["output_tokens"],
                               self.cost(hit["input_tokens"], hit["output_tokens"]), True, (time.perf_counter() - start) * 1000)
        else:
            if self.spent_usd() >= self.budget_usd:
                raise BudgetExceeded(f"estimated LLM spend reached the budget of {self.budget_usd} USD")
            try:
                text, tin, tout = self.provider.call(system, prompt, max_tokens)
            except Exception as exc:  # network, auth, rate limit: the caller falls back to extractive
                raise LLMError(f"{self.provider.name} call failed: {type(exc).__name__}") from exc
            result = LLMResult(text, self.provider.name, self.provider.model, tin, tout, self.cost(tin, tout), False,
                               (time.perf_counter() - start) * 1000)
            if path:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps({"text": text, "input_tokens": tin, "output_tokens": tout, "model": self.provider.model},
                                           ensure_ascii=False), encoding="utf-8")
        self._log(result, purpose, key)
        return result

    def _log(self, r: LLMResult, purpose: str, key: str) -> None:
        if not self.usage_log:
            return
        row = {"ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "provider": r.provider, "model": r.model,
               "purpose": purpose, "input_tokens": r.input_tokens, "output_tokens": r.output_tokens, "cost_usd": r.cost_usd,
               "cached": r.cached, "latency_ms": round(r.latency_ms, 1), "cache_key": key[:16]}
        with self._lock:
            self.usage_log.parent.mkdir(parents=True, exist_ok=True)
            with open(self.usage_log, "a", encoding="utf-8") as f:
                f.write(json.dumps(row) + "\n")


def build_llm(settings: Settings, provider: Provider | None = None) -> LLMClient | None:
    """LLM client from settings, or None when no provider/key is configured (extractive mode)."""
    if provider is None:
        key = settings.llm_api_key.get_secret_value()
        if not (settings.llm_provider and settings.llm_model and key):
            return None
        if settings.llm_provider == "openai":
            provider = OpenAIProvider(settings.llm_model, key)
        elif settings.llm_provider == "anthropic":
            provider = AnthropicProvider(settings.llm_model, key)
        else:
            raise ValueError(f"unknown LLM_PROVIDER {settings.llm_provider!r} (openai | anthropic)")
    if settings.llm_price_in_per_mtok is not None and settings.llm_price_out_per_mtok is not None:
        price = (settings.llm_price_in_per_mtok, settings.llm_price_out_per_mtok)
    else:
        price = PRICES.get(provider.model)
    return LLMClient(provider, settings.llm_cache_dir, settings.llm_usage_log, settings.llm_budget_usd, price)
