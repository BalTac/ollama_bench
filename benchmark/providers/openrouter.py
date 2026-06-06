"""OpenRouter provider — API remota https://openrouter.ai/api."""

from __future__ import annotations

import logging
import time

import requests

from benchmark.providers.base import BaseProvider, ProviderResponse

logger = logging.getLogger(__name__)


class OpenRouterProvider(BaseProvider):
    """Provider per OpenRouter API (compatibile OpenAI chat completions)."""

    def __init__(self, config: dict):
        super().__init__(config)
        self.base_url = config.get("base_url", "https://openrouter.ai/api/v1")
        self.api_key = self._resolve_api_key(config.get("api_key", ""))
        self.chat_url = f"{self.base_url}/chat/completions"

    def generate(
        self,
        prompt: str,
        model: str = "",
        temperature: float | None = None,
        response_format: dict | None = None,
    ) -> ProviderResponse:
        """Chiama OpenRouter chat completions API."""
        start = time.perf_counter()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost",
            "X-Title": "LLM Benchmark Framework",
        }
        payload: dict = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if response_format is not None:
            payload["response_format"] = response_format
        try:
            resp = requests.post(
                self.chat_url,
                headers=headers,
                json=payload,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            logger.error("OpenRouter request failed: %s", e)
            raise

        elapsed = (time.perf_counter() - start) * 1000
        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})
        response_text = message.get("content", "")
        usage = data.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)
        tokens_per_sec = completion_tokens / (elapsed / 1000) if elapsed > 0 else 0.0

        return ProviderResponse(
            text=response_text,
            prompt_tokens=prompt_tokens,
            thinking_tokens=0,
            answer_tokens=completion_tokens,
            total_tokens=total_tokens,
            latency_ms=elapsed,
            raw_response=data,
        )

    def list_models(self) -> list[str]:
        """Restituisce modelli disponibili via OpenRouter."""
        try:
            resp = requests.get(
                f"{self.base_url}/models",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            return [m["id"] for m in data.get("data", [])]
        except requests.RequestException as e:
            logger.error("OpenRouter list_models failed: %s", e)
            return []

    def is_available(self) -> bool:
        """Verifica API key configurata e connessione."""
        if not self.api_key:
            return False
        try:
            resp = requests.get(
                f"{self.base_url}/models",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=10,
            )
            return resp.status_code == 200
        except requests.RequestException:
            return False
