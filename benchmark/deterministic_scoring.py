"""Deterministic scoring — metriche oggettive NON delegate al giudice LLM.

Tutti i check deterministici sono eseguiti PRIMA del giudice.
Il giudice LLM valuta SOLO ciò che non è verificabile meccanicamente.

Prompt format (campo opzionale deterministic_checks):
{
    "deterministic_checks": {
        "exact_match": {"expected": "Parigi"},
        "json_valid": {},
        "regex_match": {"pattern": "[A-Z]{4}-\\d{4}-[a-z]{4}"},
        "expected_tools": {"tools": ["weather", "search"]},
        "expected_keywords": {"keywords": ["fattoriale", "ricorsione"], "min_matches": 1}
    }
}

Se deterministic_checks è presente → esegui tutti i check specificati.
Se assente → backward-compat: nessun check deterministico.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from benchmark.metrics import is_valid_json, extract_json_from_text

logger = logging.getLogger(__name__)

# Set dei check deterministici supportati
SUPPORTED_CHECKS = {
    "exact_match",
    "allowed_values",
    "forbidden_text",
    "json_valid",
    "required_json_keys",
    "format_valid",
    "regex_match",
    "expected_tools",
    "tool_sequence",
    "expected_keywords",
}


@dataclass
class DeterministicResults:
    """Risultati aggregati dei check deterministici."""

    exact_match: Optional[float] = None       # 0.0-1.0
    json_valid: Optional[float] = None
    format_valid: Optional[float] = None
    regex_match: Optional[float] = None
    allowed_values: Optional[float] = None
    forbidden_text: Optional[float] = None
    required_json_keys: Optional[float] = None
    expected_tools: Optional[float] = None
    tool_sequence: Optional[float] = None
    expected_keywords: Optional[float] = None
    overall: float = 0.0                      # media dei check eseguiti
    strict_compliance: float = 0.0            # media check di conformità stretta
    semantic_correctness: float = 0.0         # media check semantici
    performed_checks: list[str] = field(default_factory=list)
    details: dict[str, str] = field(default_factory=dict)


# ════════════════════════════════════════════
# Singoli check deterministici
# ════════════════════════════════════════════

def exact_match_score(response: str, config: dict) -> tuple[float, str]:
    """Confronto esatto (case-insensitive, trim)."""
    expected = config.get("expected", "")
    if not expected:
        return 0.0, "nessun valore atteso specificato"

    response_clean = response.strip().lower()
    expected_clean = expected.strip().lower()

    if response_clean == expected_clean:
        return 1.0, "exact match"
    if expected_clean in response_clean:
        return 0.7, "expected in response"
    return 0.0, f"mismatch: atteso '{expected_clean[:80]}'"


def allowed_values_score(response: str, config: dict) -> tuple[float, str]:
    """Verifica che la risposta sia uno dei valori consentiti (case-insensitive)."""
    allowed = config.get("values", config.get("allowed_values", []))
    if not isinstance(allowed, list) or not allowed:
        return 0.0, "lista allowed_values mancante"

    response_clean = response.strip().lower()
    allowed_clean = [str(v).strip().lower() for v in allowed]

    if response_clean in allowed_clean:
        return 1.0, f"valore consentito: {response.strip()}"
    return 0.0, f"valore '{response.strip()[:80]}' non consentito"


def forbidden_text_score(response: str, config: dict) -> tuple[float, str]:
    """Verifica assenza di testo vietato (case-insensitive)."""
    forbidden = config.get("texts", config.get("forbidden_text", []))
    if not isinstance(forbidden, list) or not forbidden:
        return 0.0, "lista forbidden_text mancante"

    response_lower = response.lower()
    found = [str(t) for t in forbidden if str(t).lower() in response_lower]
    if found:
        return 0.0, f"testo vietato trovato: {found[:3]}"
    return 1.0, "nessun testo vietato"


def json_valid_score(response: str, config: dict = None) -> tuple[float, str]:
    """Verifica presenza JSON valido."""
    _ = config  # unused
    if is_valid_json(response):
        return 1.0, "JSON valido"
    if extract_json_from_text(response):
        return 0.8, "JSON estratto da markdown"
    return 0.0, "nessun JSON valido"


def required_json_keys_score(response: str, config: dict) -> tuple[float, str]:
    """Verifica presenza chiavi obbligatorie in JSON."""
    required_keys = config.get("keys", config.get("required_json_keys", []))
    if not isinstance(required_keys, list) or not required_keys:
        return 0.0, "lista required_json_keys mancante"

    json_text = extract_json_from_text(response)
    if json_text is None:
        return 0.0, "nessun JSON trovato"

    try:
        data = json.loads(json_text)
    except json.JSONDecodeError:
        return 0.0, "JSON invalido"

    if not isinstance(data, dict):
        return 0.0, "JSON non è oggetto"

    missing = [k for k in required_keys if k not in data]
    if not missing:
        return 1.0, "tutte le chiavi richieste presenti"

    present_ratio = (len(required_keys) - len(missing)) / len(required_keys)
    return max(0.0, present_ratio), f"chiavi mancanti: {missing}"


def format_valid_score(response: str, config: dict) -> tuple[float, str]:
    """Verifica conformità formato (single_word, word_count_N, lowercase, ecc.)."""
    fmt = config.get("format", "").lower().strip()

    if fmt == "single_word":
        words = response.strip().split()
        if len(words) == 1:
            return 1.0, "single word"
        return 0.0, f"{len(words)} parole (attesa 1)"

    if fmt.startswith("exact_word_count_"):
        try:
            target = int(fmt.split("_")[-1])
        except ValueError:
            return 0.0, f"formato word_count non valido: {fmt}"
        words = response.strip().split()
        diff = abs(len(words) - target)
        if diff == 0:
            return 1.0, f"esattamente {target} parole"
        if diff <= 2:
            return 0.7, f"{len(words)} parole (attese {target})"
        if diff <= 5:
            return 0.4, f"{len(words)} parole (attese {target})"
        return 0.1, f"{len(words)} parole (attese {target})"

    if fmt == "lowercase":
        response_clean = response.strip()
        if response_clean == response_clean.lower():
            return 1.0, "tutto minuscolo"
        return 0.0, "contiene maiuscole"

    if fmt == "uppercase":
        response_clean = response.strip()
        if response_clean == response_clean.upper():
            return 1.0, "tutto maiuscolo"
        return 0.0, "contiene minuscole"

    # Fallback: check generico
    return 0.5, f"formato '{fmt}' non validabile deterministicamente"


def regex_match_score(response: str, config: dict) -> tuple[float, str]:
    """Verifica match regex sulla risposta."""
    pattern = config.get("pattern", "")
    if not pattern:
        return 0.0, "nessun pattern specificato"

    try:
        if re.search(pattern, response):
            return 1.0, f"regex match: {pattern[:60]}"
        return 0.0, f"regex no match: {pattern[:60]}"
    except re.error as e:
        return 0.0, f"regex invalida: {e}"


def expected_tools_score(response: str, config: dict) -> tuple[float, str]:
    """Verifica tool calling: la risposta contiene i tool attesi.

    Cerca nel JSON della risposta un campo 'tool', 'action', 'function'.
    """
    expected_tools = config.get("tools", [])
    if not expected_tools:
        return 0.0, "nessun tool atteso specificato"

    json_text = extract_json_from_text(response)
    if json_text is None:
        return 0.0, "nessun JSON trovato nella risposta"

    try:
        data = json.loads(json_text)
    except json.JSONDecodeError:
        return 0.0, "JSON invalido"

    # Cerca tool in vari campi possibili
    found_tool = None
    for key in ("tool", "action", "function", "name"):
        if key in data:
            found_tool = str(data[key]).lower()
            break
    # Anche in dict con chiave "tool" annidato
    if found_tool is None and isinstance(data, dict):
        found_tool = str(data).lower()

    if found_tool is None:
        return 0.0, "nessun campo tool/action trovato"

    expected_lower = [t.lower().strip() for t in expected_tools]
    for exp in expected_lower:
        if exp in found_tool:
            return 1.0, f"tool corretto: {exp}"
    return 0.0, f"tool '{found_tool[:50]}' non tra quelli attesi {expected_lower}"


def _extract_tool_sequence(data: Any) -> list[str]:
    """Estrae sequenza tool da payload JSON in formati comuni."""
    seq: list[str] = []

    if isinstance(data, dict):
        # Formato singolo tool
        for key in ("tool", "action", "function", "name"):
            if key in data and isinstance(data[key], (str, int, float)):
                seq.append(str(data[key]).strip().lower())
                break

        # Formato tool_calls multipli
        calls = data.get("tool_calls")
        if isinstance(calls, list):
            for call in calls:
                if not isinstance(call, dict):
                    continue
                for key in ("name", "tool", "action", "function"):
                    if key in call and isinstance(call[key], (str, int, float)):
                        seq.append(str(call[key]).strip().lower())
                        break

    return seq


def tool_sequence_score(response: str, config: dict) -> tuple[float, str]:
    """Verifica sequenza esatta di tool attesa."""
    expected = config.get("sequence", config.get("tool_sequence", []))
    if not isinstance(expected, list) or not expected:
        return 0.0, "lista tool_sequence mancante"

    json_text = extract_json_from_text(response)
    if json_text is None:
        return 0.0, "nessun JSON trovato"

    try:
        data = json.loads(json_text)
    except json.JSONDecodeError:
        return 0.0, "JSON invalido"

    found_seq = _extract_tool_sequence(data)
    if not found_seq:
        return 0.0, "nessuna sequenza tool trovata"

    expected_seq = [str(t).strip().lower() for t in expected]
    if found_seq == expected_seq:
        return 1.0, f"sequenza tool corretta: {expected_seq}"

    # Partial credit on ordered prefix
    matched_prefix = 0
    for f, e in zip(found_seq, expected_seq):
        if f == e:
            matched_prefix += 1
        else:
            break

    ratio = matched_prefix / len(expected_seq)
    return ratio, f"sequenza trovata {found_seq}, attesa {expected_seq}"


def expected_keywords_score(response: str, config: dict) -> tuple[float, str]:
    """Verifica presenza keyword nella risposta (case-insensitive)."""
    keywords = config.get("keywords", [])
    min_matches = config.get("min_matches", 1)
    if not keywords:
        return 0.0, "nessuna keyword specificata"

    response_lower = response.lower()
    matched = []
    for kw in keywords:
        if kw.lower() in response_lower:
            matched.append(kw)

    ratio = len(matched) / len(keywords)
    enough = len(matched) >= min_matches

    if ratio >= 1.0:
        return 1.0, f"tutte {len(keywords)} keyword trovate"
    if enough:
        return 0.7 + 0.3 * ratio, f"{len(matched)}/{len(keywords)} keyword (min {min_matches})"
    return 0.2 * ratio, f"{len(matched)}/{len(keywords)} keyword (min {min_matches} richieste)"


# ════════════════════════════════════════════
# Orchestratore
# ════════════════════════════════════════════

_CHECK_FUNCTIONS = {
    "exact_match": exact_match_score,
    "allowed_values": allowed_values_score,
    "forbidden_text": forbidden_text_score,
    "json_valid": json_valid_score,
    "required_json_keys": required_json_keys_score,
    "format_valid": format_valid_score,
    "regex_match": regex_match_score,
    "expected_tools": expected_tools_score,
    "tool_sequence": tool_sequence_score,
    "expected_keywords": expected_keywords_score,
}

_STRICT_CHECKS = {
    "exact_match",
    "allowed_values",
    "forbidden_text",
    "json_valid",
    "required_json_keys",
    "format_valid",
    "regex_match",
}

_SEMANTIC_CHECKS = {
    "expected_tools",
    "tool_sequence",
    "expected_keywords",
}


def run_deterministic_checks(
    response: str,
    checks: Optional[dict],
) -> DeterministicResults:
    """Esegue tutti i check deterministici configurati.

    Args:
        response: testo della risposta del modello
        checks: dict deterministic_checks dal prompt JSON, o None

    Returns:
        DeterministicResults con tutti i check eseguiti.
        Se checks è None o vuoto → overall=0, nessun check eseguito.
    """
    if not checks:
        return DeterministicResults(overall=0.0, performed_checks=[])

    results = DeterministicResults()
    values: list[float] = []
    strict_values: list[float] = []
    semantic_values: list[float] = []

    for check_name, config in checks.items():
        if check_name not in SUPPORTED_CHECKS:
            logger.warning("Check deterministico sconosciuto: '%s', ignorato", check_name)
            continue

        fn = _CHECK_FUNCTIONS.get(check_name)
        if fn is None:
            continue

        try:
            config_dict = config if isinstance(config, dict) else {}
            value, detail = fn(response, config_dict)
        except Exception as e:
            logger.error("Check '%s' fallito con errore: %s", check_name, e)
            value, detail = 0.0, f"errore: {e}"

        setattr(results, check_name, value)
        results.performed_checks.append(check_name)
        results.details[check_name] = detail
        values.append(value)
        if check_name in _STRICT_CHECKS:
            strict_values.append(value)
        if check_name in _SEMANTIC_CHECKS:
            semantic_values.append(value)

        logger.debug(
            "Check '%s': %.2f — %s", check_name, value, detail,
        )

    if values:
        results.overall = sum(values) / len(values)
    if strict_values:
        results.strict_compliance = sum(strict_values) / len(strict_values)
    if semantic_values:
        results.semantic_correctness = sum(semantic_values) / len(semantic_values)

    logger.info(
        "Deterministic checks: %d eseguiti, overall=%.3f strict=%.3f semantic=%.3f (%s)",
        len(values), results.overall, results.strict_compliance,
        results.semantic_correctness, ", ".join(results.performed_checks),
    )

    return results
