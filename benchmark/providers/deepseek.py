"""DeepSeek provider — API remota https://api.deepseek.com."""

from __future__ import annotations

import json
import logging
import time

import requests

from benchmark.providers.base import BaseProvider, ProviderResponse

logger = logging.getLogger(__name__)


class DeepSeekProvider(BaseProvider):
    """Provider per DeepSeek API (compatibile OpenAI chat completions)."""

    def __init__(self, config: dict):
        super().__init__(config)
        self.base_url = config.get("base_url", "https://api.deepseek.com")
        self.api_key = self._resolve_api_key(config.get("api_key", ""))
        self.chat_url = f"{self.base_url}/chat/completions"

    def generate(
        self,
        prompt: str,
        model: str = "deepseek-chat",
        temperature: float | None = None,
        response_format: dict | None = None,
    ) -> ProviderResponse:
        """Chiama DeepSeek chat completions API."""
        start = time.perf_counter()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
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
            logger.error("DeepSeek request failed: %s", e)
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
        """DeepSeek non espone endpoint pubblico list models. Restituisce default."""
        return ["deepseek-chat", "deepseek-reasoner"]

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
