"""Metrics extraction — metriche oggettive dalla risposta del modello."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ExtractedMetrics:
    """Metriche oggettive estratte da una risposta."""

    latency_ms: float = 0.0
    prompt_tokens: int = 0
    thinking_tokens: int = 0
    answer_tokens: int = 0
    total_tokens: int = 0
    tokens_per_sec: float = 0.0
    char_count: int = 0
    line_count: int = 0
    json_valid: int = 0          # 0/1
    format_valid: int = 0        # 0/1


def is_valid_json(text: str) -> bool:
    """Verifica se il testo contiene JSON valido (oggetto o array)."""
    text = text.strip()
    try:
        parsed = json.loads(text)
        return isinstance(parsed, (dict, list))
    except (json.JSONDecodeError, ValueError):
        # Prova a estrarre JSON da markdown code blocks
        return False


def extract_json_from_text(text: str) -> str | None:
    """Estrae JSON da testo, incluso markdown code blocks."""
    import re

    text = text.strip()

    # Prova diretto
    try:
        json.loads(text)
        return text
    except (json.JSONDecodeError, ValueError):
        pass

    # Prova ```json ... ```
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        candidate = match.group(1).strip()
        try:
            json.loads(candidate)
            return candidate
        except (json.JSONDecodeError, ValueError):
            pass

    # Prova { ... } più esterno
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        candidate = match.group(0).strip()
        try:
            json.loads(candidate)
            return candidate
        except (json.JSONDecodeError, ValueError):
            pass

    return None


def check_format_compliance(text: str, expected_format: str | None) -> bool:
    """Verifica conformità al formato atteso.

    Formati supportati:
    - 'json' → JSON valido
    - 'single_word' → una sola parola
    - 'exact_match' → (gestito separatamente nello scoring)
    - 'code_only' → contiene codice (non check rigoroso)
    - 'code' → contiene codice
    - null/None → sempre True
    """
    if expected_format is None:
        return True

    fmt = expected_format.lower().strip()

    if fmt == "json":
        return is_valid_json(text) or extract_json_from_text(text) is not None

    if fmt == "single_word":
        words = text.strip().split()
        return len(words) == 1

    if fmt in ("code", "code_only"):
        # Euristico: contiene def, class, import, ``` o indentazione significativa
        import re
        code_indicators = [
            r"\bdef\s+\w+\s*\(",
            r"\bclass\s+\w+",
            r"\bimport\s+\w+",
            r"```",
            r"\bSELECT\b.*\bFROM\b",
            r"\bfunction\s+\w+",
        ]
        return any(re.search(pat, text, re.IGNORECASE) for pat in code_indicators)

    if fmt == "sql_query":
        import re
        return bool(re.search(r"\bSELECT\b", text, re.IGNORECASE))

    if fmt == "regex":
        return True  # sempre valido, la validazione è semantica

    # Formati descrittivi: sempre True (la validazione è del giudice)
    return True


def extract_metrics(
    response_text: str,
    prompt_tokens: int = 0,
    thinking_tokens: int = 0,
    answer_tokens: int = 0,
    total_tokens: int = 0,
    latency_ms: float = 0.0,
    expected_format: str | None = None,
) -> ExtractedMetrics:
    """Estrae metriche oggettive dalla risposta.

    Combina dati dal provider (token count, latency) con analisi locale
    (caratteri, linee, JSON validity, format validity).
    """
    char_count = len(response_text)
    line_count = response_text.count("\n") + 1 if response_text else 0

    tokens_per_sec = answer_tokens / (latency_ms / 1000) if latency_ms > 0 and answer_tokens > 0 else 0.0

    json_valid = 1 if is_valid_json(response_text) else 0
    format_valid = 1 if check_format_compliance(response_text, expected_format) else 0

    return ExtractedMetrics(
        latency_ms=latency_ms,
        prompt_tokens=prompt_tokens,
        thinking_tokens=thinking_tokens,
        answer_tokens=answer_tokens,
        total_tokens=total_tokens,
        tokens_per_sec=tokens_per_sec,
        char_count=char_count,
        line_count=line_count,
        json_valid=json_valid,
        format_valid=format_valid,
    )
