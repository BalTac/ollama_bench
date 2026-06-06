"""Ollama provider — API locale http://localhost:11434."""

from __future__ import annotations

import json
import logging
import time

import requests

from benchmark.providers.base import BaseProvider, ProviderResponse

logger = logging.getLogger(__name__)


class OllamaProvider(BaseProvider):
    """Provider per Ollama locale."""

    def __init__(self, config: dict):
        super().__init__(config)
        self.base_url = config.get("base_url", "http://localhost:11434")
        self.generate_url = f"{self.base_url}/api/generate"

    def generate(
        self,
        prompt: str,
        model: str = "",
        temperature: float | None = None,
        response_format: dict | None = None,
    ) -> ProviderResponse:
        """Chiama Ollama /api/generate. model passato esternamente dal runner."""
        start = time.perf_counter()
        payload: dict = {
            "model": model,
            "prompt": prompt,
            "stream": False,
        }
        if temperature is not None:
            payload["options"] = {"temperature": temperature}
        # Align JSON-mode behavior with OpenAI-compatible providers.
        # Ollama /api/generate accepts format="json" to constrain output.
        if isinstance(response_format, dict):
            fmt_type = str(response_format.get("type", "")).strip().lower()
            if fmt_type == "json_object":
                payload["format"] = "json"
        try:
            resp = requests.post(
                self.generate_url,
                json=payload,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            logger.error("Ollama request failed: %s", e)
            raise

        elapsed = (time.perf_counter() - start) * 1000
        response_text = data.get("response", "")
        prompt_tokens = data.get("prompt_eval_count", 0)
        answer_tokens = data.get("eval_count", 0)
        total_tokens = prompt_tokens + answer_tokens
        tokens_per_sec = answer_tokens / (elapsed / 1000) if elapsed > 0 else 0.0

        return ProviderResponse(
            text=response_text,
            prompt_tokens=prompt_tokens,
            thinking_tokens=0,
            answer_tokens=answer_tokens,
            total_tokens=total_tokens,
            latency_ms=elapsed,
            raw_response=data,
        )

    def list_models(self) -> list[str]:
        """Restituisce modelli installati in Ollama."""
        try:
            resp = requests.get(
                f"{self.base_url}/api/tags",
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            return [m["name"] for m in data.get("models", [])]
        except requests.RequestException as e:
            logger.error("Ollama list_models failed: %s", e)
            return []

    def is_available(self) -> bool:
        """Verifica che Ollama sia raggiungibile."""
        try:
            resp = requests.get(self.base_url, timeout=5)
            return resp.status_code == 200
        except requests.RequestException:
            return False
