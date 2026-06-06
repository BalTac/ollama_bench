# providers package
from benchmark.providers.base import BaseProvider, ProviderResponse
from benchmark.providers.ollama import OllamaProvider
from benchmark.providers.deepseek import DeepSeekProvider
from benchmark.providers.openrouter import OpenRouterProvider
import logging

logger = logging.getLogger(__name__)

_PROVIDER_MAP = {
    "ollama": OllamaProvider,
    "deepseek": DeepSeekProvider,
    "openrouter": OpenRouterProvider,
}


def get_provider(name: str, config: dict) -> BaseProvider:
    """Factory: restituisce provider by name configurato."""
    provider_class = _PROVIDER_MAP.get(name)
    if provider_class is None:
        raise ValueError(
            f"Provider sconosciuto: '{name}'. Disponibili: {list(_PROVIDER_MAP)}"
        )
    provider_config = config.get("providers", {}).get(name, {})
    logger.info("Provider '%s' inizializzato", name)
    return provider_class(provider_config)


def list_available_providers() -> list[str]:
    """Elenco provider registrati."""
    return list(_PROVIDER_MAP)
