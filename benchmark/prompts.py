"""Prompt loader — carica e valida prompt JSON da directory."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = {"id", "prompt"}
OPTIONAL_FIELDS = {
    "category", "subcategory", "weight", "expected_format",
    "expected_answer", "expected_behavior",
}


class PromptValidationError(Exception):
    """Errore di validazione prompt."""
    pass


def validate_prompt(prompt: dict, source_file: str = "") -> None:
    """Valida schema minimo di un prompt. Solleva PromptValidationError."""
    if not isinstance(prompt, dict):
        raise PromptValidationError(f"Prompt non è un dict in {source_file}")

    missing = REQUIRED_FIELDS - set(prompt)
    if missing:
        raise PromptValidationError(
            f"Campi obbligatori mancanti {missing} in {source_file}: {prompt.get('id', '?')}"
        )

    prompt_id = prompt["id"]
    if not isinstance(prompt_id, str) or not prompt_id.strip():
        raise PromptValidationError(f"Prompt id vuoto o non stringa in {source_file}")

    prompt_text = prompt["prompt"]
    if not isinstance(prompt_text, str) or not prompt_text.strip():
        raise PromptValidationError(f"Prompt '{prompt_id}': testo vuoto in {source_file}")

    weight = prompt.get("weight", 1.0)
    if not isinstance(weight, (int, float)) or weight <= 0:
        raise PromptValidationError(
            f"Prompt '{prompt_id}': weight deve essere > 0, trovato {weight}"
        )


def load_prompts(prompts_dir: str | Path) -> list[dict]:
    """Carica tutti i prompt JSON ricorsivamente. Valida ogni prompt.

    Restituisce lista di dict pronti per il database.
    """
    prompts_dir = Path(prompts_dir)
    if not prompts_dir.is_dir():
        logger.warning("Directory prompt non trovata: %s", prompts_dir)
        return []

    all_prompts: list[dict] = []
    errors: list[str] = []

    for json_file in sorted(prompts_dir.rglob("*.json")):
        file_str = str(json_file.relative_to(prompts_dir))
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            logger.error("JSON invalido in %s: %s", file_str, e)
            errors.append(f"JSON invalido: {file_str}")
            continue

        items = data if isinstance(data, list) else [data]
        for item in items:
            try:
                validate_prompt(item, file_str)
                # Deriva category/subcategory dal path se non specificati
                if "category" not in item:
                    item["category"] = json_file.parent.name
                if "subcategory" not in item:
                    item["subcategory"] = json_file.stem
                all_prompts.append(item)
            except PromptValidationError as e:
                logger.error("%s", e)
                errors.append(str(e))

    if errors:
        logger.warning("Caricati %d prompt con %d errori di validazione",
                       len(all_prompts), len(errors))

    return all_prompts


def get_prompts_by_category(
    prompts_dir: str | Path, category: str
) -> list[dict]:
    """Carica solo prompt di una categoria specifica."""
    all_prompts = load_prompts(prompts_dir)
    return [p for p in all_prompts if p.get("category") == category]


def list_available_categories(prompts_dir: str | Path) -> list[str]:
    """Elenca categorie disponibili da struttura directory."""
    prompts_path = Path(prompts_dir)
    if not prompts_path.is_dir():
        return []

    categories: set[str] = set()
    for item in prompts_path.iterdir():
        if item.is_dir() and not item.name.startswith("."):
            categories.add(item.name)
    return sorted(categories)
