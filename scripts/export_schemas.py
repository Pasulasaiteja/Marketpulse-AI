"""Regenerate contracts/schemas/*.schema.json from the Pydantic models.

Run:  python scripts/export_schemas.py
A test (tests/test_contracts.py) fails if the committed files are out of date.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from marketpulse.contracts.models import CONTRACT_MODELS  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "src" / "marketpulse" / "contracts" / "schemas"


def render(name: str) -> str:
    schema = CONTRACT_MODELS[name].model_json_schema()
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name in CONTRACT_MODELS:
        (OUT / f"{name}.schema.json").write_text(render(name), encoding="utf-8")
        print("wrote", name)


if __name__ == "__main__":
    main()
