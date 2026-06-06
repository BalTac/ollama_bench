"""Provider base class + response dataclass.

Ogni provider deve implementare BaseProvider.
"""

from __future__ import annotations

import logging
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


# ── .env loader (zero dipendenze) ──────────

def load_dotenv(dotenv_path: str | Path = ".env") -> None:
    """Carica file .env in os.environ. Non sovrascrive variabili già impostate.

    Formato supportato:
      KEY=value
      KEY="value with spaces"
      # commento
    """
    env_path = Path(dotenv_path)
    if not env_path.is_file():
        return

    loaded = 0
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip("\"'")  # rimuovi quoting opzionale

        if key and key not in os.environ:
            os.environ[key] = val
            loaded += 1

    if loaded:
        logger.info(".env caricato: %d variabili da %s", loaded, env_path)


# Carica .env all'import del modulo (eseguito una volta sola)
load_dotenv()


@dataclass
class ProviderResponse:
    """Risposta normalizzata da qualsiasi provider."""

    text: str
    prompt_tokens: int = 0
    thinking_tokens: int = 0
    answer_tokens: int = 0
    total_tokens: int = 0
    latency_ms: float = 0.0
    raw_response: dict = field(default_factory=dict)


class BaseProvider(ABC):
    """Interfaccia comune per tutti i provider."""

    def __init__(self, config: dict):
        self.config = config
        self.timeout = config.get("timeout", 120)

    @abstractmethod
    def generate(
        self,
        prompt: str,
        model: str = "",
        temperature: float | None = None,
        response_format: dict | None = None,
    ) -> ProviderResponse:
        """Invia prompt e restituisce risposta normalizzata.

        Args:
            prompt: testo del prompt
            model: nome modello (provider-specific)
            temperature: temperatura sampling (None = default provider)
            response_format: es. {"type": "json_object"} per JSON mode
        """
        ...

    @abstractmethod
    def list_models(self) -> list[str]:
        """Restituisce elenco modelli disponibili."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Verifica che il provider sia raggiungibile."""
        ...

    def _resolve_api_key(self, value: str) -> str:
        """Risolve ${ENV_VAR} da variabili d'ambiente.

        Le variabili possono essere impostate in .env, variabili d'ambiente
        reali, o export con $env:VAR in PowerShell.
        """
        match = re.match(r"^\$\{(.+)\}$", value)
        if match:
            env_var = match.group(1)
            resolved = os.environ.get(env_var, "")
            if not resolved:
                logger.warning(
                    "Variabile d'ambiente %s non impostata. "
                    "Crea un file .env dalla copia di .env.example",
                    env_var,
                )
            return resolved
        return value
