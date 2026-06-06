"""Judge — modello giudice provider-agnostic.

Usa temperature=0 e JSON mode per output deterministico.
Parsing JSON diretto, senza euristiche markdown.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Optional

from benchmark.providers.base import BaseProvider

logger = logging.getLogger(__name__)

JUDGE_SYSTEM_PROMPT = """Sei un giudice imparziale per valutare risposte di Large Language Models.

VALUTI SOLO aspetti soggettivi non verificabili meccanicamente.
NON valutare: validità JSON, exact match, conformità formato, presenza tool.
Questi aspetti sono già verificati da controlli deterministici.

Riceverai:
1. Il prompt originale
2. La risposta del modello da valutare
3. (Informativo) Risultati dei check deterministici già eseguiti

Restituisci ESCLUSIVAMENTE un JSON con questo schema:
{
  "accuracy": <float 0.0-1.0>,
  "reasoning": <float 0.0-1.0>,
  "coding": <float 0.0-1.0>,
  "hallucination_risk": <float 0.0-1.0>,
  "overall": <float 0.0-1.0>,
  "notes": "<breve spiegazione in italiano>"
}

Criteri:
- accuracy: correttezza e accuratezza fattuale della risposta
- reasoning: qualità del ragionamento logico, coerenza, profondità
- coding: qualità del codice prodotto (0 se non applicabile)
- hallucination_risk: 0 = nessuna allucinazione, 1 = completamente inventato
- overall: valutazione complessiva soggettiva

Non aggiungere testo prima o dopo il JSON. Solo il JSON."""


# Schema atteso per validazione post-parse
EXPECTED_SCHEMA = {
    "accuracy": (int, float),
    "reasoning": (int, float),
    "coding": (int, float),
    "hallucination_risk": (int, float),
    "overall": (int, float),
    "notes": str,
}


@dataclass
class JudgeScore:
    """Score prodotto dal giudice (SOLO metriche soggettive)."""

    accuracy: float = 0.0
    reasoning: float = 0.0
    coding: float = 0.0
    hallucination_risk: float = 0.0
    overall: float = 0.0
    notes: str = ""


class JudgeParseError(Exception):
    """Errore di parsing o validazione dell'output del giudice."""
    def __init__(self, message: str, raw_text: str = ""):
        super().__init__(message)
        self.raw_text = raw_text


class Judge:
    """Giudice provider-agnostic per valutazione risposte.

    Usa temperature=0 + JSON mode per massima affidabilità.
    """

    def __init__(
        self,
        provider: BaseProvider,
        model: str,
        max_retries: int = 1,
    ):
        self.provider = provider
        self.model = model
        self.max_retries = max_retries

    def evaluate(
        self,
        prompt_text: str,
        response_text: str,
        deterministic_info: Optional[str] = None,
        expected_format: Optional[str] = None,
        expected_answer: Optional[str] = None,
        expected_behavior: Optional[str] = None,
    ) -> JudgeScore:
        """Valuta SOLO metriche soggettive.

        expected_format/expected_answer/expected_behavior: deprecati,
        la validazione oggettiva è gestita da deterministic_scoring.
        Mantenuti per backward compat.
        """

        judge_prompt = self._build_judge_prompt(
            prompt_text, response_text, deterministic_info,
        )

        logger.info(
            "Judge chiamata: model=%s, prompt_len=%d, response_len=%d",
            self.model, len(prompt_text), len(response_text),
        )
        logger.debug("Judge prompt:\n%s", judge_prompt[:2000])

        last_raw = ""

        for attempt in range(self.max_retries + 1):
            try:
                response = self.provider.generate(
                    prompt=judge_prompt,
                    model=self.model,
                    temperature=0.0,
                    response_format={"type": "json_object"},
                )

                last_raw = response.text

                logger.info(
                    "Judge risposta ricevuta: %d char, latency=%.0fms",
                    len(response.text), response.latency_ms,
                )
                logger.debug("Judge raw response:\n%s", response.text[:2000])

                score = self._parse_score(response.text)
                logger.info(
                    "Judge score OK: accuracy=%.2f reasoning=%.2f coding=%.2f "
                    "hallucination=%.2f overall=%.2f (attempt %d/%d)",
                    score.accuracy, score.reasoning, score.coding,
                    score.hallucination_risk, score.overall,
                    attempt + 1, self.max_retries + 1,
                )
                return score

            except (JudgeParseError, json.JSONDecodeError, ValueError) as e:
                logger.warning(
                    "Judge parse error (attempt %d/%d): %s\nRaw: %s",
                    attempt + 1, self.max_retries + 1, e, last_raw[:500],
                )
                if attempt >= self.max_retries:
                    logger.error(
                        "Judge fallito dopo %d retry. Last raw: %s",
                        self.max_retries + 1, last_raw[:1000],
                    )
                    raise
            except Exception as e:
                logger.error("Judge request failed: %s", e)
                raise

        raise RuntimeError("Judge evaluation failed")

    def _build_judge_prompt(
        self,
        prompt_text: str,
        response_text: str,
        deterministic_info: Optional[str] = None,
    ) -> str:
        """Costruisce il prompt per il giudice."""
        parts = [
            JUDGE_SYSTEM_PROMPT,
            "",
            "---",
            "",
            "PROMPT ORIGINALE:",
            prompt_text,
            "",
            "RISPOSTA DA VALUTARE:",
            response_text,
        ]

        if deterministic_info:
            parts.append("")
            parts.append("CHECK DETERMINISTICI GIÀ ESEGUITI (non rivalutarli):")
            parts.append(deterministic_info)

        parts.append("")
        parts.append("---")
        parts.append("Restituisci ESCLUSIVAMENTE il JSON di valutazione. Nessun altro testo.")
        return "\n".join(parts)

    def _parse_score(self, raw_text: str) -> JudgeScore:
        """Parsa JSON diretto (no markdown stripping) + validazione schema.

        Raises:
            JudgeParseError: se parsing o validazione fallisce.
        """
        raw_text = raw_text.strip()
        logger.debug("_parse_score: raw_text (%d char):\n%s", len(raw_text), raw_text[:1500])

        # 1. Parse JSON diretto
        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError as e:
            logger.error("_parse_score: JSON invalido. Raw: %s", raw_text[:500])
            raise JudgeParseError(
                f"JSON invalido: {e}", raw_text,
            ) from e

        if not isinstance(data, dict):
            raise JudgeParseError(
                f"Atteso dict JSON, ricevuto {type(data).__name__}", raw_text,
            )

        logger.info("_parse_score: campi JSON trovati: %s", sorted(data.keys()))

        # 2. Validazione schema: campi obbligatori
        missing = []
        for field, expected_types in EXPECTED_SCHEMA.items():
            if field not in data:
                missing.append(field)

        if missing and "notes" in missing:
            missing.remove("notes")  # notes è opzionale
            data["notes"] = ""

        if missing:
            msg = f"Campi obbligatori mancanti: {missing}"
            logger.error("_parse_score: %s. Keys: %s", msg, sorted(data.keys()))
            raise JudgeParseError(msg, raw_text)

        # 3. Validazione tipi
        type_errors = []
        for field, expected_types in EXPECTED_SCHEMA.items():
            if field not in data:
                continue
            value = data[field]
            if not isinstance(value, expected_types):
                type_errors.append(
                    f"{field}: atteso {expected_types}, ricevuto {type(value).__name__} ({value})"
                )

        if type_errors:
            msg = "Errori di tipo: " + "; ".join(type_errors)
            logger.error("_parse_score: %s", msg)
            raise JudgeParseError(msg, raw_text)

        # 4. Clamp range 0-1 per campi numerici
        numeric_fields = ("accuracy", "reasoning", "coding", "hallucination_risk", "overall")
        for field in numeric_fields:
            value = data.get(field, 0.0)
            logger.debug("_parse_score: %s = %s (type=%s)", field, value, type(value).__name__)
            if not (0.0 <= value <= 1.0):
                logger.warning(
                    "_parse_score: %s fuori range [0,1] (%.4f), clamp in corso",
                    field, value,
                )
                data[field] = max(0.0, min(1.0, value))

        score = JudgeScore(
            accuracy=float(data.get("accuracy", 0.0)),
            reasoning=float(data.get("reasoning", 0.0)),
            coding=float(data.get("coding", 0.0)),
            hallucination_risk=float(data.get("hallucination_risk", 0.0)),
            overall=float(data.get("overall", 0.0)),
            notes=str(data.get("notes", "")),
        )

        logger.info(
            "_parse_score OK: overall=%.3f, accuracy=%.3f, reasoning=%.3f",
            score.overall, score.accuracy, score.reasoning,
        )
        return score
