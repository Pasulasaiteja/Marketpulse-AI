"""Boundary validation: JSON Schema (structural) + Pydantic (semantic).

Use ``validate_payload("ForecastOutput", obj)`` at every module boundary.
Non-Python members can validate against ``contracts/schemas/*.json``; the
extra semantic rules (sums, ordering, no leakage) are documented in CONTRACT.md.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
from pydantic import BaseModel

from marketpulse.contracts.models import CONTRACT_MODELS

SCHEMA_DIR = Path(__file__).parent / "schemas"


class ContractViolation(ValueError):
    """Raised when a payload does not satisfy a contract."""


def load_schema(name: str) -> dict[str, Any]:
    return json.loads((SCHEMA_DIR / f"{name}.schema.json").read_text(encoding="utf-8"))


def validate_payload(name: str, payload: Any) -> BaseModel:
    """Validate ``payload`` (dict or model) against contract ``name``; return the model."""
    if name not in CONTRACT_MODELS:
        raise KeyError(f"unknown contract {name!r}")
    model_cls = CONTRACT_MODELS[name]
    data = payload.model_dump(mode="json") if isinstance(payload, BaseModel) else payload
    try:
        jsonschema.validate(data, load_schema(name))
        return model_cls.model_validate(data)
    except (jsonschema.ValidationError, ValueError) as exc:
        raise ContractViolation(f"{name}: {exc}") from exc
